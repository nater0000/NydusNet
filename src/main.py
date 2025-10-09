import customtkinter as ctk
from app import App  # Import the main application class from app.py
from utils.logger import setup_logger

def main():
    """
    Main function to initialize and run the NydusNet application.
    """
    # 1. Set up global logging for the application
    setup_logger()

    # 2. Set the appearance mode for CustomTkinter
    ctk.set_appearance_mode("System")  # Options: "System", "Dark", "Light"
    ctk.set_default_color_theme("blue") # Options: "blue", "green", "dark-blue"

    # 3. Create the main application instance
    app = App()

    # 4. Start the Tkinter main loop to run the application
    app.mainloop()

if __name__ == "__main__":
    main()
