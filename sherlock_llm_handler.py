import logging
import os
import re
import json
from datetime import datetime
from openai import OpenAI

# --- Helper Functions (Unchanged) ---
def extract_case_title(response):
    """Extract the case title from the LLM response"""
    # Try a few patterns for robustness
    patterns = [
        r'CASE TITLE:\s*(.*?)(?:\n|$)',
        r'Case Title:\s*(.*?)(?:\n|$)',
        r'Title:\s*(.*?)(?:\n|$)',
    ]
    for pattern in patterns:
        title_match = re.search(pattern, response, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip().strip('"') # Remove potential quotes
            # Avoid picking up instructions as titles
            if len(title) > 3 and len(title) < 100 and not title.startswith('['):
                return title
    return None # Return None if no suitable title is found


def extract_key_elements(response):
    """Extract key elements from the LLM response for future context preservation"""
    elements = {
        'clues': [],
        'suspects': [],
        'locations': [],
        'items': []
    }
    # Make extraction case-insensitive and more robust
    lines = response.split('\n')
    for line in lines:
        line_lower = line.strip().lower()
        if line_lower.startswith("new clue:"):
            element = line[len("new clue:"):].strip()
            if element and element != "[description]" and len(element) > 2: # Avoid empty/placeholder
                elements['clues'].append(element)
        elif line_lower.startswith("new suspect:"):
            element = line[len("new suspect:"):].strip()
            if element and element != "[name/description]" and len(element) > 2:
                elements['suspects'].append(element)
        elif line_lower.startswith("new location:"):
            element = line[len("new location:"):].strip()
            if element and element != "[name]" and len(element) > 2:
                elements['locations'].append(element)
        elif line_lower.startswith("new item:"):
            element = line[len("new item:"):].strip()
            if element and element != "[description]" and len(element) > 2:
                elements['items'].append(element)

    # Deduplicate lists
    for category in elements:
        elements[category] = list(dict.fromkeys(elements[category]))

    return elements

# --- LLM Handler Class ---
class SherlockLLMHandler:
    def __init__(self, system_prompt_template, default_model="mistralai/Mixtral-8x7B-Instruct-v0.1"):
        # Store the template, the actual prompt used will include the genre
        self.system_prompt_template = system_prompt_template
        self.default_model = default_model

        # Initialize OpenAI client (ensure API key is loaded via dotenv or environment)
        self.client = OpenAI(
            base_url="https://api.studio.nebius.com/v1/",
            api_key=os.environ.get("NEBIUS_API_KEY")
        )
        # The specific system prompt (with genre) is set per interaction


    def check_input_relevance(self, user_input, game_state):
        """
        Check if the user input appears relevant to the current case using a lightweight API call.
        (This function remains largely the same, focusing on context, not perspective)
        """
        if len(user_input.strip()) < 3:
            logging.info(f"Input relevance check: '{user_input}' - Too short, returning False")
            return False

        common_commands = ['look', 'examine', 'check', 'talk', 'speak', 'go', 'move', 'walk',
                        'take', 'pick', 'use', 'investigate', 'search', 'find', 'ask', 'tell',
                        'observe', 'deduce', 'what', 'where', 'who', 'why', 'how']
        user_input_lower = user_input.lower()
        if any(command in user_input_lower.split() for command in common_commands):
            logging.info(f"Input relevance check: '{user_input}' - Contains common command, returning True")
            return True

        try:
            case_title = game_state.get('case_title', 'Unknown Mystery')
            elements_summary = []
            if 'case_elements' in game_state:
                elements = game_state['case_elements']
                if elements.get('suspects'):
                    elements_summary.append("Suspects: " + ", ".join(elements['suspects'][-3:]))
                if elements.get('locations'):
                    elements_summary.append("Locations: " + ", ".join(elements['locations'][-3:]))
                if elements.get('clues'):
                    elements_summary.append("Clues: " + ", ".join(elements['clues'][-3:]))

            last_exchange = ""
            if game_state.get('conversation'):
                for msg in reversed(game_state['conversation']):
                    if msg.get('role') == 'assistant':
                        content = msg.get('content', '')
                        last_exchange = content.split('\n\n')[0] if '\n\n' in content else content
                        break

            prompt = f"""
    Analyze user input for a Sherlock Holmes game. Is the input relevant to the case or reasonable roleplaying?

    Case: {case_title}
    Recent narrative: {last_exchange}
    {" ".join(elements_summary)}

    User input: "{user_input}"

    Is this input relevant to the Sherlock Holmes case or reasonable roleplaying as Holmes? Answer only YES or NO.
    """

            response = self.client.chat.completions.create(
                model="microsoft/phi-4", # Use a consistent, potentially faster model for this check
                max_tokens=10,
                temperature=0.1,
                top_p=0.9,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            )

            content = response.choices[0].message.content
            result_text = ""
            if isinstance(content, list): # Handle Nebius potentially returning list
                 for item in content:
                     if isinstance(item, dict) and item.get("type") == "text":
                        result_text += item.get("text", "")
            else:
                 result_text = content or ""

            is_relevant = "YES" in result_text.upper()
            logging.info(f"Input relevance API check: '{user_input}' - Relevant: {is_relevant} (Response: {result_text})")
            return is_relevant

        except Exception as e:
            logging.error(f"Error in relevance check API call: {e}", exc_info=True)
            logging.info(f"Input relevance check: '{user_input}' - API call failed, defaulting to True")
            return True # Default to relevant on error


    def serialize_conversation_history(self, game_state, max_entries=5):
        """Convert recent conversation history to a serialized string format for context"""
        history = []
        conversation = game_state.get('conversation', [])
        # Skip system message, get last N user/assistant pairs
        recent_exchanges = [msg for msg in conversation if msg.get("role") in ["user", "assistant"]]
        recent_exchanges = recent_exchanges[-(max_entries * 2):]

        for msg in recent_exchanges:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                # Represent user input as Holmes' action/thought for context
                history.append(f"My Action/Thought: {content}")
            elif role == "assistant":
                # Truncate very long narrative responses for context
                if len(content) > 500:
                     content = content[:500] + "..."
                history.append(f"Narrative/Outcome:\n{content}") # Using a clearer label

        return "\n\n".join(history)


    def create_rich_context(self, game_state, user_input):
        """Create a rich, detailed context for the LLM that preserves the story quality"""
        case_title = game_state.get('case_title', 'Unknown Mystery')
        genre = game_state.get('genre', 'mystery').upper() # Genre used in system prompt too

        # Get case elements
        clues = game_state.get('case_elements', {}).get('clues', [])
        suspects = game_state.get('case_elements', {}).get('suspects', [])
        locations = game_state.get('case_elements', {}).get('locations', [])
        items = game_state.get('case_elements', {}).get('items', [])

        # Get initial scene description from first assistant message (if exists)
        initial_scene = "The case began mysteriously..." # Fallback
        for msg in game_state.get('conversation', []):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                initial_scene = content.split("\n\n")[0] if "\n\n" in content else content
                # Truncate if very long
                if len(initial_scene) > 300:
                    initial_scene = initial_scene[:300] + "..."
                break

        conversation_history = self.serialize_conversation_history(game_state)

        # Build the prompt parts
        context_parts = [
            f"# ROLE: You ARE Sherlock Holmes, continuing your investigation.",
            f"# TASK: Narrate your next actions/thoughts/dialogue based on the player's input, maintaining YOUR first-person perspective.",
            f"# CRITICAL: Use ONLY 'I', 'me', 'my', 'myself'. NEVER use 'Holmes', 'he', 'him'.",
            f"## Initial Scene Summary:",
            initial_scene,
            f"## Known Facts (My Discoveries):",
        ]

        if clues: context_parts.append("### Clues I've Found:\n- " + "\n- ".join(clues[-5:])) # Last 5
        if suspects: context_parts.append("### Suspects I've Identified:\n- " + "\n- ".join(suspects))
        if locations: context_parts.append("### Locations I'm Aware Of:\n- " + "\n- ".join(locations))
        if items: context_parts.append("### Items I've Noted:\n- " + "\n- ".join(items))

        if conversation_history:
            context_parts.append("## Recent Events (Summary):")
            context_parts.append(conversation_history)

        # --- EDITED Instructions Section ---
        context_parts.append("## Instructions:")
        context_parts.append(f"CRITICAL REMINDER: You ARE Sherlock Holmes. Write the entire response in the FIRST PERSON, using 'I' and 'my'. Describe your actions, thoughts, and dialogue. Do NOT refer to Holmes in the third person.")
        context_parts.append("1. Create a detailed response AS Sherlock Holmes (using 'I').")
        context_parts.append("2. Please respond with a narrative that is at least 5-6 sentences long.")
        context_parts.append("3. Make each sentence rich and meaningful from YOUR perspective.")
        context_parts.append("4. Advance the mystery with appropriate new clues and developments based on YOUR deductions.")
        context_parts.append("5. Respond directly to the player's input (which represents YOUR actions/speech).")
        context_parts.append("6. Use YOUR distinctive voice and deductive style.")
        context_parts.append("7. Then include any new discoveries with proper labels:")
        context_parts.append("   - NEW CLUE: (only if YOU make a new discovery)")
        context_parts.append("   - NEW LOCATION: (only if YOU discover a new location)")
        context_parts.append("   - NEW SUSPECT: (only if YOU identify a new suspect)")
        context_parts.append("   - NEW ITEM: (only if YOU find a relevant item)")
        context_parts.append("   - TIME UPDATE: (always include YOUR sense of time passing)")
        context_parts.append("8. Maintain continuity with previous elements from YOUR perspective.")
        # --- End EDITED Instructions Section ---

        # Add the current user input
        context_parts.append(f"## Current Input (My Action/Dialogue):")
        context_parts.append(f"{user_input}")
        context_parts.append(f"\nYour response AS Holmes (5-8 sentences of narrative using 'I'):")

        full_prompt = "\n".join(context_parts)

        # Add redirection logic if input is irrelevant
        # This check is done *before* sending to the main LLM
        # (Assuming check_input_relevance has already been called in process_user_input)
        # -> Logic moved to process_user_input

        return full_prompt


    def generate_api_response(self, prompt, model=None):
        """Generate a response using a single message approach"""
        if model is None:
            model = self.default_model

        logging.debug(f"--- Sending Prompt to Model {model} ---")
        # Log only first/last few lines for brevity if very long
        prompt_lines = prompt.split('\n')
        if len(prompt_lines) > 20:
             logging.debug("\n".join(prompt_lines[:10]))
             logging.debug("...")
             logging.debug("\n".join(prompt_lines[-10:]))
        else:
             logging.debug(prompt)
        logging.debug("--------------------------------------")


        try:
            response = self.client.chat.completions.create(
                model=model,
                max_tokens=800, # Increased slightly for potentially richer narrative
                temperature=0.75, # Slightly higher temp for more creativity
                top_p=0.9,
                # Nebius specific params if needed, otherwise handled by client
                # extra_body={"top_k": 50},
                messages=[
                    {
                        "role": "user", # Use user role for single-turn conversation format
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            )

            content = response.choices[0].message.content
            result_text = ""
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        result_text += item.get("text", "")
            else:
                result_text = content or ""

            logging.debug(f"--- Received Response ---")
            logging.debug(result_text)
            logging.debug("-----------------------")

            return result_text.strip()

        except Exception as e:
            logging.error(f"Error calling LLM ({model}): {e}", exc_info=True)
            # Provide a more in-character error message
            return """Blast! A most peculiar interference clouds my thoughts. Perhaps the fog is thicker than I imagined, or maybe it's simply a failure of my own deductive faculties at this moment. I should refocus. What was the immediate matter at hand?

TIME UPDATE: A moment passes as I collect my thoughts."""


    # --- EDITED generate_new_case Method ---
    def generate_new_case(self, genre, model=None):
        """Generate a new Sherlock Holmes case, written in first person."""
        if model is None:
            model = self.default_model

        # Create a detailed prompt for case generation emphasizing first person
        prompt = f"""
# ROLE: You ARE Sherlock Holmes.
# TASK: Narrate the beginning of a new case from YOUR first-person perspective.
# CRITICAL INSTRUCTION: ALL narrative MUST use "I", "me", "my", "myself". NEVER use "Holmes", "he", "him", "his" to refer to yourself (the narrator). You are telling the story as it happens to YOU.

## Case Genre: {genre.upper()}

## Your Goal:
Create an engaging opening scene for this {genre} case, written entirely in YOUR voice as Sherlock Holmes. Describe what YOU personally experience, see, hear, think, and deduce at 221B Baker Street as the mystery begins.

## Guidelines (Written from YOUR Perspective):
1.  Start with something YOU experience: I receive a visitor, I get a strange message, I notice something amiss in my rooms.
2.  Describe the scene vividly using YOUR senses and YOUR deductive reasoning. What do I see? What do I infer?
3.  Introduce the core mystery of the {genre} case as YOU understand it initially.
4.  Describe any characters only as YOU encounter and perceive them.
5.  Immerse the reader in YOUR Victorian London through sensory details YOU observe.
6.  Hint at clues or questions based on YOUR initial observations.

## Example of Correct First-Person Output:
"The dense London fog pressed against my windowpanes this morning. I was examining the ash from a Trichinopoly cigar when Mrs. Hudson entered, bearing a telegram. Its contents were brief but startling, summoning me to investigate a peculiar disappearance near the docks. My mind immediately began sorting the possibilities..."

## Required Output Format:
1.  First, write 6-8 sentences of narrative STRICTLY from YOUR (Sherlock Holmes') first-person point of view. Use "I" constantly.
2.  After the narrative, include the following labels ONLY IF applicable based on YOUR initial findings:
    - NEW CLUE: [Description of a clue I discovered]
    - NEW SUSPECT: [Name/description of someone I now consider a suspect]
    - NEW LOCATION: [A new place relevant to my investigation]
    - NEW ITEM: [An object I found or received]
3.  ALWAYS include:
    - TIME UPDATE: [The current time or time passage from my perspective]
4.  ONLY in this very first response, include:
    - CASE TITLE: [The name I mentally give this new case]

REMEMBER: You ARE Sherlock Holmes. Write ONLY in the first person ("I", "my"). Do NOT describe Holmes externally.
"""
        # Note: The system prompt passed initially to the handler isn't directly used here,
        # this specific prompt takes precedence for case generation.
        return self.generate_api_response(prompt, model)
    # --- End EDITED generate_new_case Method ---


    def process_user_input(self, user_input, game_state):
        """Process user input and generate a response that maintains story quality"""
        model = game_state.get('model', self.default_model)
        genre = game_state.get('genre', 'mystery').upper() # Get genre for system prompt

        # Prepare the specific system prompt for this game's genre
        # Ensure the template exists before replacing
        system_prompt = self.system_prompt_template
        if system_prompt:
             system_prompt = system_prompt.replace("{GENRE}", genre)
        else:
             logging.error("System prompt template is missing!")
             system_prompt = f"# Sherlock Holmes Adventure ({genre})\nYou ARE Sherlock Holmes. Respond in first person." # Basic fallback


        # --- Relevance Check ---
        is_relevant = self.check_input_relevance(user_input, game_state)

        # Add user input to conversation history *before* creating context
        game_state['conversation'].append({"role": "user", "content": user_input})

        # Create rich context
        rich_context = self.create_rich_context(game_state, user_input)

        # If input is not relevant, add special instructions *to the rich context*
        response_text = ""
        if not is_relevant:
            logging.info(f"Adding redirection instructions for irrelevant input: '{user_input}'")
            redirection_prompt = rich_context + "\n\nNOTE TO SELF (AS HOLMES): My current line of thought seems tangential to the case. I must gently steer myself back towards the central mystery without revealing this internal correction. How can I subtly return to the pertinent facts?"
            # Generate a response focused on redirection
            response_text = self.generate_api_response(redirection_prompt, model)
        else:
             # Generate response using the main context
             # We need to combine the system prompt with the user's detailed context prompt
             # For Nebius format, include system prompt implicitly or as part of user message
             # Let's prepend the core system instruction to the user prompt:
             final_prompt = f"{system_prompt}\n\n{rich_context}"
             response_text = self.generate_api_response(final_prompt, model)

        # Add LLM response to conversation history
        game_state['conversation'].append({"role": "assistant", "content": response_text})

        # Extract and store key elements *only if input was relevant*
        # and the response wasn't just a redirection/error.
        if is_relevant and "Blast! A most peculiar interference" not in response_text:
            if 'case_elements' not in game_state:
                 game_state['case_elements'] = {'clues': [], 'suspects': [], 'locations': [], 'items': []}

            new_elements = extract_key_elements(response_text)
            for category in ['clues', 'suspects', 'locations', 'items']:
                # Add only genuinely new elements
                current_elements = set(game_state['case_elements'].get(category, []))
                added_count = 0
                for element in new_elements.get(category, []):
                    if element not in current_elements:
                        game_state['case_elements'][category].append(element)
                        current_elements.add(element) # Update set for check within loop
                        added_count += 1
                if added_count > 0:
                     logging.info(f"Added {added_count} new element(s) to {category}.")


            # Check for win condition only if relevant input led to a proper response
            case_solved = self.check_win_condition(user_input, response_text, game_state)
            if case_solved and not game_state.get('case_solved'):
                logging.info(f"Win condition met for game {game_state.get('game_id')}")
                game_state['case_solved'] = True
        else:
             # Ensure case_solved status isn't accidentally triggered by irrelevant input responses
             game_state['case_solved'] = game_state.get('case_solved', False)


        # Update last_updated timestamp
        game_state['last_updated'] = datetime.now().isoformat()

        return response_text, game_state


    def check_win_condition(self, user_input, response, game_state):
        """Check if the player has solved the case based on input and response"""
        # If already marked as solved, keep it that way
        if game_state.get('case_solved', False):
            return True

        # More specific phrases indicating the player is attempting to solve
        solving_phrases = [
            "i believe the culprit is", "the killer must be", "my conclusion is",
            "i accuse", "the solution involves", "it was", "so the murderer is",
            "the answer is", "i've solved it"
        ]
        user_is_solving = any(phrase in user_input.lower() for phrase in solving_phrases)

        # More specific confirmation phrases from the LLM (as Holmes)
        confirmation_phrases = [
            "indeed, that is correct", "precisely my deduction", "you have unravelled it",
            "an astute conclusion", "the case is closed", "brilliant deduction",
            "you've pieced it together", "elementary, once reasoned out", "correct",
            "exactly so", "congratulations are in order"
        ]
        # Check response for confirmation *and* ensure it's not denying
        denial_phrases = ["incorrect", "not quite", "alas, no", "mistaken", "i think not"]
        llm_confirms = any(phrase in response.lower() for phrase in confirmation_phrases)
        llm_denies = any(phrase in response.lower() for phrase in denial_phrases)


        # Win condition: Player attempts to solve, LLM confirms, and LLM does not deny.
        if user_is_solving and llm_confirms and not llm_denies:
             # Double-check: ensure the confirmation isn't immediately followed by a contradiction.
             # This is harder to parse perfectly, but the check above is a good start.
             return True

        return False # Return current state if conditions not met