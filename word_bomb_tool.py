import requests
import time
import random
import pyautogui

class WordBombTool:
    def __init__(self):
        """Initialize the cheat tool with word dictionary"""
        print("\n" + "="*60)
        print("Word Bomb Tool v1.0")
        print("GitHub           : https://github.com/mPhpMaster")
        print("Discord          : alhlack")
        print("="*60 + "\n")
        self.search_mode = None
    
    def find_matching_words(self, available_letters):
        """Find all valid words that contain the given input string using Datamuse API."""
        if not available_letters:
            return []
        
        # Construct the query based on the selected search mode
        if self.search_mode == 'starts':
            query = f"{available_letters}*"
        elif self.search_mode == 'ends':
            query = f"*{available_letters}"
        else:  # contains
            query = f"*{available_letters}*"
            
        url = f"https://api.datamuse.com/words?sp={query}"
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            # The API returns results sorted by score, so we can use them directly.
            # The user requested to "resort", so we will explicitly sort by score descending.
            results = response.json()
            results.sort(key=lambda x: x.get('score', 0), reverse=True)
            
            return [item['word'] for item in results]
        except requests.exceptions.RequestException as e:
            print(f"Error fetching words from API: {e}")
            return []

    def analyze_letters(self, letters):
        """
        Analyze given letters and provide suggestions.
        Returns new letters if provided by the user during typing, otherwise None.
        """
        letters = letters.lower().strip()
        print(f"\nAnalyzing letters: {letters}")
        
        matching_words = self.find_matching_words(letters)
        
        if matching_words:
            # Determine how many words to pick (up to 10)
            num_to_pick = min(len(matching_words), 10)
            words_to_type = random.sample(matching_words, num_to_pick)
            
            print(f"Found words: {', '.join(words_to_type)}")

            print("Switching windows and typing in 1 second...")
            time.sleep(0.1)
            pyautogui.hotkey('alt', 'tab')
            time.sleep(0.1) # A small pause after switching

            words_to_type.reverse()
            for word in words_to_type:
                pyautogui.typewrite(word, interval=0.1)
                pyautogui.press('enter')
                
                # Switch back to ask for user confirmation
                pyautogui.hotkey('alt', 'tab')
                time.sleep(0.1)
                
                user_input = input("Press ENTER for next word, or enter new letters: ").strip()
                if user_input:
                    # User entered new letters, stop typing and return them.
                    print("New letters received. Starting new search...")
                    return user_input
                
                pyautogui.hotkey('alt', 'tab')
                time.sleep(0.1)
            
            # After the loop, if it wasn't interrupted by new input
            pyautogui.hotkey('alt', 'tab') # Switch back to console one last time
            print("Finished typing all suggested words. Ready for new letters.\n")

        else:
            print("No valid word found!\n")
        return None

    def start(self):
        """Start the interactive cheat tool"""
        # Mode selection at the start
        while self.search_mode is None:
            print("\nSelect a search mode:")
            print("  1: Starts with")
            print("  2: Ends with")
            print("  3: Contains")
            choice = input("Enter your choice (1, 2, or 3): ").strip()
            if choice == '1':
                self.search_mode = 'starts'
            elif choice == '2':
                self.search_mode = 'ends'
            elif choice == '3':
                self.search_mode = 'contains'
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

        print(f"\nMode set to: '{self.search_mode}'. Enter letters to find words (type 'quit' to exit).")
        print("-"*60)
        while True:
            try:
                letters = input("Enter letters: ").strip()
                
                if letters.lower() == 'quit':
                    print("\nExiting Word Bomb Tool v1.0...")
                    break
                
                if not letters:
                    print("Please enter at least one letter.\n")
                    continue
                
                # Validate input - only alphabetic characters
                if not all(c.isalpha() or c.isspace() for c in letters):
                    print("Please enter only letters.\n")
                    continue
                
                new_letters = self.analyze_letters(letters)
                while new_letters:
                    # If analyze_letters returned new input, re-run analysis
                    new_letters = self.analyze_letters(new_letters)

                
            except KeyboardInterrupt:
                print("\n\nExiting Word Bomb Tool v1.0...")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue


if __name__ == "__main__":
    cheat = WordBombTool()
    cheat.start()
