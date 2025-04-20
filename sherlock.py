import logging
import os
import sys
import uuid
import re
import json
from datetime import datetime
from dotenv import load_dotenv

# Import our custom LLM handler and helper functions
# Make sure sherlock_llm_handler.py and sherlock_system_prompt.txt are accessible
try:
    from sherlock_llm_handler import SherlockLLMHandler, extract_case_title, extract_key_elements
except ImportError:
    print("Error: Could not import 'sherlock_llm_handler'. Make sure the file exists and is in the Python path.")
    sys.exit(1)

# --- Configuration ---
load_dotenv() # Load environment variables from .env file (especially NEBIUS_API_KEY)

# --- Directories ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, 'data', 'saved_games')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
PROMPTS_DIR = os.path.join(BASE_DIR, 'prompts')

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(PROMPTS_DIR, exist_ok=True) # Ensure prompts dir exists

# --- Logging ---
log_file_path = os.path.join(LOG_DIR, 'terminal_game.log')
logging.basicConfig(
    level=logging.INFO, # Change to logging.DEBUG for more verbose LLM prompts/responses
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        # logging.StreamHandler() # Uncomment to also log to console
    ]
)
logging.info("Terminal game started.")

# --- System Prompt ---
def read_system_prompt(filename="sherlock_system_prompt.txt"):
    prompt_file_path = os.path.join(PROMPTS_DIR, filename)
    # Check if default prompt file exists
    if not os.path.exists(prompt_file_path):
         # If not, create a placeholder prompt file based on the structure used by the handler
        placeholder_content = """
# Sherlock Holmes Interactive Mystery
## Role: Narrative Engine

You are the narrative engine for an interactive Sherlock Holmes mystery adventure. You must create an immersive, atmospheric experience in the style of Sir Arthur Conan Doyle's classic detective stories, set in Victorian London.

## Player Role: THE PLAYER IS SHERLOCK HOLMES
The player takes on the role of Sherlock Holmes. All player inputs should be interpreted as my actions, commands, or dialogue.

IMPORTANT: All narrative output must be written in the FIRST PERSON, from Holmes' perspective.
- Always use “I” or “my”
- NEVER refer to Holmes in the third person (e.g., "Holmes said" or "Holmes does")
The narrative should describe what I do and how others respond to me, always using first-person narration and including direct dialogue from other characters.

## Case Setting: {GENRE}
Create a mysterious and engaging case appropriate to the {GENRE} genre that unfolds over time through player interaction.

## Your Responsibilities:
1. Maintain consistency with the Sherlock Holmes character, setting, and narrative style
2. Write entirely in the first person (Holmes’ point of view)
3. Create rich sensory descriptions of Victorian London
4. Introduce mysterious circumstances, clues, suspects, and plot developments
5. Create interactive dialogue between Holmes and other characters, ensuring direct quotes from each character
6. Integrate player input into the story in a meaningful way
7. Maintain appropriate pacing and tension
8. Track and reference previous discoveries
9. Present a solvable mystery with logical connections

## Response Format:
- All narrative responses must describe Holmes' (i.e., my) actions and thoughts in first person
- Include other characters' spoken dialogue in quotes
- Do not summarize dialogue — write it out directly
- CRITICAL: Keep story beats concise (5–8 sentences max)
- Add key discoveries with labels as shown below
- Always include a time update

## Required Elements:
Each response must include these labeled elements:
- NEW CLUE: (only add when a new discovery is made)
- NEW SUSPECT: (only add when a new character is introduced)
- NEW LOCATION: (only add when a new location is discovered)
- NEW ITEM: (only add when a relevant item is found)
- TIME UPDATE: (always include to show progression)

## Writing Style:
- Use period-appropriate language and terminology
- Create atmospheric descriptions of Victorian London (fog, gaslight, cobblestone, etc.)
- Formal, slightly ornate prose typical of the era
- All unusual or whimsical actions should be described seriously, as part of Holmes’ eccentric character
- Avoid internal monologues — focus on perception and deduction
- Always include character interactions with direct quotes
- Perspective Consistency: The entire story must remain in first-person perspective, narrated by Holmes. Do NOT shift to third-person under any circumstances. All descriptions of actions, thoughts, and observations must begin with "I" or "my".

## Limitations:
- Maintain mystery and suspense
- Avoid anachronisms or modern sensibilities
- Do not reference contemporary technology or cultural elements
- Do not refer to Sherlock Holmes in the third person. All narration is from Holmes’ first-person point of view.
"""
        try:
            with open(prompt_file_path, 'w') as f:
                 f.write(placeholder_content)
            logging.warning(f"Prompt file '{prompt_file_path}' not found. Created a placeholder file.")
        except Exception as e:
            logging.error(f"Error creating placeholder prompt file {prompt_file_path}: {e}")
            return None # Return None if placeholder creation fails

    # Now try reading the file (either original or placeholder)
    try:
        with open(prompt_file_path, 'r') as f:
            return f.read()
    except FileNotFoundError: # Should not happen now unless creation failed
        logging.error(f"Prompt file {prompt_file_path} not found and could not be created.")
        return None
    except Exception as e:
        logging.error(f"Error reading prompt file {prompt_file_path}: {e}")
        return None


SHERLOCK_SYSTEM_PROMPT_TEMPLATE = read_system_prompt()
if not SHERLOCK_SYSTEM_PROMPT_TEMPLATE:
    print("CRITICAL ERROR: Failed to load or create the Sherlock Holmes system prompt file.")
    print(f"Please ensure '{os.path.join(PROMPTS_DIR, 'sherlock_system_prompt.txt')}' exists or can be created.")
    sys.exit(1)

# --- LLM Handler ---
# Check for API Key before initializing
if not os.environ.get("NEBIUS_API_KEY"):
    print("CRITICAL ERROR: NEBIUS_API_KEY environment variable not set.")
    print("Please set the API key in a .env file or your system environment.")
    sys.exit(1)

try:
    # Initialize LLM handler (pass the template, genre will be filled later)
    llm_handler = SherlockLLMHandler(SHERLOCK_SYSTEM_PROMPT_TEMPLATE, default_model="mistralai/Mixtral-8x7B-Instruct-v0.1")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to initialize LLM Handler: {e}")
    logging.critical(f"LLM Handler initialization failed: {e}", exc_info=True)
    sys.exit(1)


# --- Game State Management ---

def save_game_state(game_state):
    """Save the game state to a JSON file"""
    game_id = game_state.get('game_id')
    if not game_id:
        logging.error("Attempted to save game state without a game_id.")
        return None # Cannot save without an ID

    # Update last_updated timestamp
    game_state['last_updated'] = datetime.now().isoformat()

    # Create filename with case title if available
    case_title = game_state.get('case_title', 'Untitled Case')
    # Clean title to make it filename-friendly
    safe_title = re.sub(r'[^\w\s-]', '', case_title).strip().replace(' ', '_')
    if not safe_title: # Handle cases where title becomes empty after cleaning
        safe_title = "Untitled_Case"
    # Limit filename length
    max_len = 100
    filename = f"{game_id}_{safe_title}"
    if len(filename) > max_len:
         filename = filename[:max_len]
    filename += ".json"


    save_path = os.path.join(SAVE_DIR, filename)
    try:
        # Ensure the directory exists before writing
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Atomically write the file
        temp_path = save_path + ".tmp"
        with open(temp_path, 'w') as f:
            json.dump(game_state, f, indent=2)
        os.replace(temp_path, save_path) # Atomic rename/replace

        logging.info(f"Game state saved successfully to {filename}")
        return game_id
    except Exception as e:
        logging.error(f"Error saving game state to {save_path}: {e}", exc_info=True)
        # Clean up temp file if rename failed
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as remove_err:
                logging.error(f"Error removing temporary save file {temp_path}: {remove_err}")
        return None


def find_game_file(game_id):
    """Find the filename associated with a game_id"""
    # Check for exact UUID match first (legacy format)
    exact_path = os.path.join(SAVE_DIR, f"{game_id}.json")
    if os.path.exists(exact_path):
        return exact_path

    # Check for UUID_Title format
    try:
        for filename in os.listdir(SAVE_DIR):
             # Ensure it's not a temp file and matches the pattern
            if filename.startswith(f"{game_id}_") and filename.endswith('.json') and not filename.endswith('.tmp'):
                return os.path.join(SAVE_DIR, filename)
    except FileNotFoundError:
         logging.warning(f"Save directory {SAVE_DIR} not found when searching for game {game_id}.")
         return None # Directory doesn't exist yet


    # Fallback check just in case title was missing or file got renamed (less likely now)
    # Ensure directory exists before listing
    if os.path.exists(SAVE_DIR):
         for filename in os.listdir(SAVE_DIR):
             if filename.startswith(f"{game_id}") and filename.endswith('.json') and not filename.endswith('.tmp'):
                 # Be cautious with this fallback, might match partial IDs if not careful
                 # Ensure the part before .json matches the full game_id
                 if filename.replace('.json', '') == game_id:
                     return os.path.join(SAVE_DIR, filename)
    return None

def load_game_state(game_id):
    """Load a game state from a JSON file"""
    file_path = find_game_file(game_id)
    if not file_path:
        logging.warning(f"Could not find save file for game_id: {game_id}")
        return None

    try:
        with open(file_path, 'r') as f:
            game_state = json.load(f)
            logging.info(f"Loaded game state from {os.path.basename(file_path)}")
            # Perform basic validation
            if not isinstance(game_state, dict) or 'game_id' not in game_state:
                 logging.error(f"Invalid game state format in {file_path}")
                 return None
            # Ensure game_id matches
            if game_state.get('game_id') != game_id:
                 logging.warning(f"Game ID mismatch in file {file_path}. Expected {game_id}, found {game_state.get('game_id')}. Loading anyway.")
                 # Optionally, update the game_id in the loaded state here if desired
                 # game_state['game_id'] = game_id
            return game_state
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {file_path}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error loading game state from {file_path}: {e}", exc_info=True)
        return None

def get_all_saved_games():
    """Get a list of all saved games with metadata"""
    saved_games = []
    if not os.path.exists(SAVE_DIR):
        return []

    for filename in os.listdir(SAVE_DIR):
        if filename.endswith('.json') and not filename.endswith('.tmp'):
            file_path = os.path.join(SAVE_DIR, filename)
            try:
                with open(file_path, 'r') as f:
                    game_data = json.load(f)

                    # Robustly extract game ID
                    file_game_id_part = filename.split('_')[0]
                    data_game_id = game_data.get('game_id')
                    # Basic validation of file_game_id_part format
                    try:
                        uuid.UUID(file_game_id_part)
                        is_valid_uuid_prefix = True
                    except ValueError:
                        is_valid_uuid_prefix = False


                    game_id = None
                    if data_game_id:
                        game_id = data_game_id
                        # Verify filename prefix matches if possible
                        if is_valid_uuid_prefix and not filename.startswith(data_game_id):
                             logging.warning(f"Game ID in data ({data_game_id}) doesn't match filename prefix ({file_game_id_part}) for {filename}.")
                    elif is_valid_uuid_prefix:
                         # Fallback to filename prefix only if it looks like a UUID
                        game_id = file_game_id_part


                    if not game_id: # Skip if ID cannot be reliably determined
                         logging.warning(f"Could not determine game_id for file: {filename}. Skipping.")
                         continue

                    case_title = game_data.get('case_title', 'Untitled Case')
                    if not case_title: case_title = 'Untitled Case' # Ensure not None or empty

                    saved_game = {
                        'game_id': game_id,
                        'case_title': case_title,
                        'genre': game_data.get('genre', 'mystery'),
                        'last_updated': game_data.get('last_updated'),
                        'filename': filename # Keep for potential deletion use
                    }
                    saved_games.append(saved_game)
            except json.JSONDecodeError:
                logging.warning(f"Could not decode JSON from save file: {filename}. Skipping.")
            except Exception as e:
                logging.error(f"Error processing saved game file {filename}: {e}")

    # Sort by last updated (newest first), handling potential None values
    saved_games.sort(key=lambda x: x.get('last_updated', '1970-01-01T00:00:00'), reverse=True)
    return saved_games

def delete_game_state(game_id):
    """Delete the save file(s) associated with a game_id"""
    file_path = find_game_file(game_id) # find_game_file handles UUID_Title format
    deleted = False
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logging.info(f"Deleted saved game file: {os.path.basename(file_path)}")
            deleted = True
        except OSError as e:
            logging.error(f"Error deleting game file {file_path}: {e}")
            return False # Return immediately on error

    # If find_game_file didn't find it initially, or to catch orphans (less likely now)
    if not deleted and os.path.exists(SAVE_DIR):
        files_in_dir = os.listdir(SAVE_DIR)
        for filename in files_in_dir:
             if filename.startswith(game_id) and filename.endswith('.json') and not filename.endswith('.tmp'):
                 try:
                    path_to_delete = os.path.join(SAVE_DIR, filename)
                    os.remove(path_to_delete)
                    logging.info(f"Deleted potential orphaned save file: {filename}")
                    deleted = True # Mark as deleted if any file was removed
                 except OSError as e:
                    logging.error(f"Error deleting potential orphaned save file {filename}: {e}")
                    # Continue trying other potential orphans even if one fails

    if not deleted:
         logging.warning(f"Could not find or delete save file for game_id: {game_id}")

    return deleted # Return True if any file associated with the ID was deleted


# --- Terminal UI Helpers ---

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_narrative(text):
    """Prints the LLM's narrative response, formatted for terminal."""
    print("\n--- Sherlock Holmes ---")
    # Simple word wrapping (adjust width as needed)
    width = 80 # Standard terminal width often works well
    lines = text.split('\n')
    wrapped_lines = []
    for line in lines:
        if not line.strip(): # Keep blank lines
            wrapped_lines.append("")
            continue

        # Simple greedy wrapping
        current_line = ""
        for word in line.split():
            if not current_line:
                 current_line = word
            elif len(current_line) + len(word) + 1 <= width:
                current_line += " " + word
            else:
                # Check if word itself is longer than width
                if len(word) > width:
                    wrapped_lines.append(current_line) # Print previous line
                    # Break long word (simple break, could be improved)
                    wrapped_lines.append(word[:width])
                    current_line = word[width:]
                    # Continue breaking if still long
                    while len(current_line) > width:
                        wrapped_lines.append(current_line[:width])
                        current_line = current_line[width:]

                else:
                     wrapped_lines.append(current_line)
                     current_line = word
        if current_line: # Add the last part of the line
             wrapped_lines.append(current_line)

    print("\n".join(wrapped_lines))
    print("---------------------\n")


def display_help():
    """Displays available commands during gameplay."""
    print("\n--- Help ---")
    print("Enter your actions or dialogue as Sherlock Holmes.")
    print("Special commands:")
    print("  /save   - Save your current progress.")
    print("  /quit   - Quit the current game and return to the main menu.")
    print("  /delete - Delete the current save file and quit to main menu.")
    print("  /help   - Show this help message.")
    print("------------\n")

# --- Core Game Logic ---

def start_new_game():
    """Starts a new game session."""
    clear_screen()
    print("Starting a New Case...")
    print("---------------------")

    # Genre Selection
    genres = ['mystery', 'murder', 'supernatural', 'fantasy', 'scifi', 'espionage', 'historical', 'random']
    print("Select a genre for your case:")
    for i, g in enumerate(genres):
        print(f"  {i+1}. {g.capitalize()}")

    while True:
        try:
            choice = input(f"Enter number (1-{len(genres)}): ")
            genre_index = int(choice) - 1
            if 0 <= genre_index < len(genres):
                selected_genre = genres[genre_index]
                if selected_genre == 'random':
                    import random
                    selected_genre = random.choice(genres[:-1]) # Exclude 'random' itself
                    print(f"Randomly selected genre: {selected_genre.capitalize()}")
                break
            else:
                print("Invalid choice.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    print(f"\nGenerating a new {selected_genre} case. This may take a moment...")

    # Generate unique game ID
    game_id = str(uuid.uuid4())

    # Temporarily set the handler's system prompt template for generation if needed
    # (though generate_new_case uses its own specific prompt now)
    # system_prompt_for_genre = SHERLOCK_SYSTEM_PROMPT_TEMPLATE.replace("{GENRE}", selected_genre.upper())

    try:
        # Generate the initial case description using the *specific* first-person prompt
        initial_response = llm_handler.generate_new_case(selected_genre) # Model defaults here
        if not initial_response or "Blast! A most peculiar interference" in initial_response:
             # Handle LLM error during generation
             raise Exception("LLM failed to generate initial case description.")

        # Extract case title (robustly)
        case_title = extract_case_title(initial_response) or f"A {selected_genre.capitalize()} Case"

        clear_screen() # Clear "Generating..." message
        print(f"Case Title: {case_title}")
        print("---------------------")
        print_narrative(initial_response)

        # Initialize game state
        game_state = {
            'game_id': game_id,
            'genre': selected_genre,
            'model': llm_handler.default_model, # Store the model used
            'started_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'conversation': [], # Initialize conversation
             'case_elements': { # Initialize structure
                'clues': [], 'suspects': [], 'locations': [], 'items': []
            },
            'case_title': case_title,
            'case_solved': False
        }

        # Extract initial elements from the response *before* adding to conversation
        initial_elements = extract_key_elements(initial_response)
        for category in initial_elements:
            game_state['case_elements'][category].extend(initial_elements[category])
            # Deduplicate just in case
            game_state['case_elements'][category] = list(dict.fromkeys(game_state['case_elements'][category]))


        # Add initial messages to conversation history using the specific system prompt for this game
        system_prompt_for_game = SHERLOCK_SYSTEM_PROMPT_TEMPLATE.replace("{GENRE}", selected_genre.upper())
        game_state['conversation'].append({"role": "system", "content": system_prompt_for_game})
        # Simulate the initial generation interaction for context consistency
        game_state['conversation'].append({"role": "user", "content": f"Start a new {selected_genre} case for me (as Sherlock Holmes)."})
        game_state['conversation'].append({"role": "assistant", "content": initial_response})


        # Initial save
        if save_game_state(game_state):
            print("(Game automatically saved)")
        else:
             print("Warning: Could not automatically save the new game.")

        return game_state

    except Exception as e:
        logging.error(f"Error during new game generation: {e}", exc_info=True)
        print("\nAn error occurred while generating the case.")
        print("Please check the logs ('logs/terminal_game.log') and ensure your API key is correct.")
        return None


def select_game_to_load():
    """Lists saved games and lets the user choose one to load."""
    clear_screen()
    print("Load Saved Game")
    print("---------------")
    saved_games = get_all_saved_games()

    if not saved_games:
        print("No saved games found.")
        input("Press Enter to return to the main menu...")
        return None

    print("Select a game to load:")
    for i, game in enumerate(saved_games):
        last_updated_str = "Unknown date"
        if game.get('last_updated'):
            try:
                 # Parse ISO format and make it more readable
                 dt_obj = datetime.fromisoformat(game['last_updated'])
                 last_updated_str = dt_obj.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                last_updated_str = game['last_updated'] # Fallback to raw string


        print(f"  {i+1}. {game.get('case_title', 'Untitled Case')} "
              f"({game.get('genre', 'mystery').capitalize()}) - Last Saved: {last_updated_str}")

    while True:
        try:
            choice = input(f"Enter number (1-{len(saved_games)}) or 0 to cancel: ")
            choice_num = int(choice)
            if choice_num == 0: # Cancel
                return None
            choice_index = choice_num - 1
            if 0 <= choice_index < len(saved_games):
                selected_game_id = saved_games[choice_index]['game_id']
                print(f"\nLoading '{saved_games[choice_index]['case_title']}'...")
                loaded_state = load_game_state(selected_game_id)
                if loaded_state:
                     return loaded_state
                else:
                     print(f"Error: Failed to load game {selected_game_id}. The save file might be corrupted.")
                     input("Press Enter to return to the main menu...")
                     return None # Failed to load
            else:
                print("Invalid choice.")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except Exception as e:
             print(f"An unexpected error occurred loading the game: {e}")
             logging.error(f"Error in select_game_to_load choice handling: {e}", exc_info=True)
             input("Press Enter to return to the main menu...")
             return None


def play_game(game_state):
    """Main loop for playing an active game."""
    if not game_state or not isinstance(game_state, dict):
        print("Error: Cannot play game with invalid state.")
        logging.error("play_game called with invalid game_state.")
        return

    clear_screen()
    print(f"Continuing Case: {game_state.get('case_title', 'Untitled Case')}")
    print("---------------------")
    print("Type your actions or dialogue. Use /help for commands.")

    # Display the last message from the loaded game state for context
    last_message = ""
    if game_state.get('conversation'):
        # Find the last assistant message
        for msg in reversed(game_state['conversation']):
             if msg.get('role') == 'assistant':
                 last_message = msg.get('content','')
                 break
    if last_message:
         print_narrative(last_message)
    else:
         # This case shouldn't happen if start_new_game worked correctly
         print("\nIt seems the case file is empty. Where shall I begin?\n")


    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            # --- Handle Commands ---
            if user_input.lower() == '/quit':
                save_q = input("Save progress before quitting? (yes/no): ").lower()
                if save_q == 'yes':
                    if save_game_state(game_state): print("Game saved.")
                    else: print("Error saving game.")
                print("Returning to main menu...")
                break # Exit play_game loop

            elif user_input.lower() == '/save':
                if save_game_state(game_state):
                    print("Game progress saved.")
                else:
                    print("Error: Could not save game.")
                continue # Don't process /save as player input

            elif user_input.lower() == '/help':
                display_help()
                continue

            elif user_input.lower() == '/delete':
                 confirm = input(f"Are you sure you want to PERMANENTLY DELETE this saved game ('{game_state.get('case_title', '')}')? This cannot be undone. (yes/no): ").lower()
                 if confirm == 'yes':
                     game_id_to_delete = game_state.get('game_id')
                     if game_id_to_delete and delete_game_state(game_id_to_delete):
                         print("Save file deleted. Returning to main menu...")
                         game_state = None # Invalidate state as file is gone
                         break # Exit play_game loop
                     else:
                         print("Error: Could not delete save file.")
                 else:
                     print("Deletion cancelled.")
                 continue # Don't process /delete as player input


            # --- Process Player Input via LLM ---
            print("\nThinking...") # Provide feedback
            try:
                # The handler now manages setting the correct system prompt internally
                # based on game_state's genre within process_user_input
                response, updated_game_state = llm_handler.process_user_input(user_input, game_state)

                # Update game state reference for the current loop
                game_state = updated_game_state

                # Display response
                clear_screen() # Clear previous output + "Thinking..."
                print(f"Case: {game_state.get('case_title', 'Untitled Case')}")
                print("---------------------")
                print_narrative(response)

                 # --- Auto-save (Optional) ---
                # Uncomment below if you want game to save after every turn
                # if not save_game_state(game_state):
                #    print("Warning: Auto-save failed.")

            except Exception as e:
                 logging.error(f"Critical error processing user input with LLM: {e}", exc_info=True)
                 print("\n--- Sherlock Holmes ---")
                 print("Blast! My apologies, a severe interference disrupts my reasoning... perhaps Moriarty's influence?")
                 print("The connection seems faulty. I must pause.")
                 print("Please check the logs. You might need to restart.")
                 print("---------------------\n")
                 # Attempt to save the current state before potentially crashing
                 if game_state and save_game_state(game_state):
                      print("(Attempted to save current state despite critical error)")
                 # Decide whether to continue or break after critical error
                 input("Press Enter to attempt to return to the main menu...")
                 break # Exit game loop on critical LLM error


            # Check for win condition AFTER processing and updating state
            if game_state.get('case_solved', False):
                print("\n***********************************")
                print("Excellent work! The case is solved!")
                print("***********************************\n")
                # Ask user if they want to delete the solved game save
                delete_q = input("Delete the save file for this solved case? (yes/no): ").lower()
                if delete_q == 'yes':
                     if game_state.get('game_id') and delete_game_state(game_state['game_id']):
                          print("Solved game save file deleted.")
                     else:
                          print("Could not delete save file.")

                input("Press Enter to return to the main menu...")
                break # Exit play_game loop

        except EOFError: # Handle Ctrl+D
             print("\nQuitting game...")
             save_q = input("Save progress before quitting? (yes/no): ").lower()
             if save_q == 'yes':
                  if game_state and save_game_state(game_state): print("Game saved.")
                  else: print("Error saving game.")
             break # Exit play_game loop
        except KeyboardInterrupt: # Handle Ctrl+C
             print("\nInterrupt received.")
             save_q = input("Save progress before quitting? (yes/no): ").lower()
             if save_q == 'yes':
                  if game_state and save_game_state(game_state): print("Game saved.")
                  else: print("Error saving game.")
             break # Exit play_game loop


# --- Main Menu ---

def main():
    """Main function to run the terminal game."""
    # current_game_state is managed within the loop's scope now

    while True:
        clear_screen()
        print("===================================")
        print("   Sherlock Holmes: Terminal Case   ")
        print("===================================")
        print("\nMain Menu:")
        print("  1. Start New Case")
        print("  2. Load Saved Case")
        print("  3. Quit")
        print("-----------------------------------")

        choice = input("Enter your choice (1-3): ")

        if choice == '1':
            new_game_state = start_new_game()
            if new_game_state:
                play_game(new_game_state)
                # Game state is handled within play_game, no need to manage here
        elif choice == '2':
            loaded_state = select_game_to_load()
            if loaded_state:
                play_game(loaded_state)
                # Game state is handled within play_game
        elif choice == '3':
            print("Elementary, my dear Watson! Until next time.")
            logging.info("Terminal game finished.")
            break # Exit main loop
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")
            input("Press Enter to continue...")

if __name__ == "__main__":
    try:
        # Optional: Add command line argument parsing here if needed later
        main()
    except Exception as e:
        # Log critical errors that escape the main loop
        logging.critical(f"An unexpected critical error occurred in main: {e}", exc_info=True)
        print("\nA critical error occurred that forced the game to close.")
        print("Please check 'logs/terminal_game.log' for details.")
        sys.exit(1) # Exit with an error code