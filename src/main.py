import customtkinter as ctk
from app import App
from utils.logger import setup_logger

def main():
    """
    Main function to initialize and run the NydusNet application.
    """
    setup_logger()
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()