# Sherlock Holmes: AI-powered Interactive Adventure

Welcome to **Sherlock Holmes: Interactive Adventure**, an interactive text-based adventure game powered by AI! Step into the shoes of the world's greatest detective and solve mysteries generated dynamically by a Large Language Model (LLM) accessed via the Nebius API.

Experience Victorian London, gather clues, interrogate suspects, and use your deductive prowess – all narrated in the **first-person perspective** as if you *are* Sherlock Holmes.

## Features ✨

*   **Play as Sherlock Holmes:** Immerse yourself in the role with a unique first-person narrative style.
*   **AI-Generated Mysteries:** Each case is dynamically created by an LLM, offering unique scenarios.
*   **Genre Selection:** Choose from various genres like Mystery, Murder, Supernatural, Sci-Fi, and more for diverse cases.
*   **Interactive Gameplay:** Your typed actions and dialogue directly influence the story's progression.
*   **Atmospheric Setting:** Explore the foggy streets and gaslit alleys of Victorian London.
*   **Save & Load:** Save your progress at any time and resume your investigation later.
*   **Case Tracking:** The game automatically extracts and remembers key clues, suspects, locations, and items.
*   **In-Game Commands:** Use `/save`, `/quit`, `/delete`, and `/help` for game management.

## Live-Demo

[https://suenkler-ai.de/sherlock](https://suenkler-ai.de/sherlock)

## Requirements 📋

*   Python 3.7+
*   A Nebius AI API Key (obtainable from Nebius AI) or another OpenAI-compatible API.

## Installation ⚙️

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/sherlock-terminal-case.git # Replace with your repo URL
    cd sherlock-terminal-case
    ```

2.  **Create a virtual environment (Recommended):**
    *   On macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration 🔑

1.  **Create a `.env` file** in the root directory of the project (`sherlock-terminal-case`).
2.  **Add your Nebius API key** to the `.env` file like this:

    ```dotenv
    # .env file
    NEBIUS_API_KEY="YOUR_NEBIUS_API_KEY_HERE"
    ```

    Replace `"YOUR_NEBIUS_API_KEY_HERE"` with your actual key.

3.  **Security:** Ensure your `.env` file is listed in your `.gitignore` file to prevent accidentally committing your API key to version control. A basic `.gitignore` should include:

    ```gitignore
    # .gitignore
    venv/
    __pycache__/
    *.pyc
    *.log
    .env
    data/saved_games/*.tmp # Ignore temp save files
    ```

## Running the Game ▶️

1.  Make sure you are in the project's root directory (`sherlock-terminal-case`) in your terminal and that your virtual environment (if created) is active.
2.  Run the main script:
    ```bash
    python sherlock.py
    ```
3.  Follow the on-screen prompts in the main menu to start a new case or load a saved one.

## Gameplay 🎮

*   The game will present narrative scenarios from Holmes' first-person perspective.
*   When prompted with `>`, type what you (as Holmes) want to do or say. Examples:
    *   `Examine the muddy footprints near the window.`
    *   `Ask Mrs. Hudson if she saw anyone suspicious enter the building.`
    *   `Go to Scotland Yard.`
    *   `"My dear Watson, observe the distinct lack of dust on this mantelpiece!"`
*   Use the following commands during gameplay:
    *   `/save`: Saves your current game progress.
    *   `/quit`: Quits the current game (prompts to save) and returns to the main menu.
    *   `/delete`: Permanently deletes the current game's save file and returns to the main menu.
    *   `/help`: Displays the available commands.
*   The story progresses based on your inputs and the LLM's responses. New clues, suspects, locations, and items will be highlighted.

## File Structure 📁

```
sherlock-terminal-case/
├── .env # Your API key (You create this)
├── .gitignore # Specifies intentionally untracked files
├── data/
│ └── saved_games/ # Stores saved game state (.json files)
├── logs/
│ └── terminal_game.log # Log file for debugging
├── prompts/
│ └── sherlock_system_prompt.txt # Core instructions for the LLM persona
├── requirements.txt # Python dependencies
├── sherlock.py # Main game application script
└── sherlock_llm_handler.py # Module for handling LLM communication
```

## Customization 🔧

You can tailor the AI's behavior by editing the `prompts/sherlock_system_prompt.txt` file. This file contains the core instructions given to the LLM regarding its role, narrative style, required elements, and constraints.

## Contributing 🤝

Contributions are welcome! If you have suggestions for improvements or find bugs, please feel free to open an issue or submit a pull request.

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details.
