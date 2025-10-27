import customtkinter as ctk
import logging

class HistoryView(ctk.CTkFrame):
    """
    The history view, allowing users to browse the version history of
    configuration files.
    """
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent") # Blend with content area
        self.controller = controller

        # Configure grid layout
        self.grid_columnconfigure(2, weight=1) # Right-most column (content viewer) expands
        self.grid_rowconfigure(0, weight=1) # Content row expands vertically

        # --- Panes ---
        # File Browser (left pane)
        self.file_browser_frame = ctk.CTkScrollableFrame(self, label_text="Configuration Files")
        self.file_browser_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew") # Gridded to row 0

        # Version Timeline (middle pane)
        self.version_timeline_frame = ctk.CTkScrollableFrame(self, label_text="File History")
        self.version_timeline_frame.grid(row=0, column=1, padx=5, pady=10, sticky="nsew") # Gridded to row 0

        # Content Viewer (right pane) - initially hidden
        self.content_viewer = ctk.CTkTextbox(self, state="disabled", wrap="none", font=("Courier New", 12))
        # This will be gridded in _on_version_select

    def on_enter(self):
        """Called by the main controller when this view is shown to refresh data."""
        logging.info("Entering History View.")
        self._populate_file_browser()
        # Clear other panes when entering
        self._clear_timeline()
        self._clear_content_viewer()

    def _clear_timeline(self):
        """Removes all widgets from the version timeline frame."""
        for widget in self.version_timeline_frame.winfo_children():
            widget.destroy()
        # Add a placeholder if needed after clearing
        # ctk.CTkLabel(self.version_timeline_frame, text="Select a file...").pack(padx=10, pady=10)

    def _clear_content_viewer(self):
        """Clears the content viewer textbox and hides it."""
        if self.content_viewer.winfo_exists():
            self.content_viewer.configure(state="normal")
            self.content_viewer.delete("1.0", "end")
            self.content_viewer.configure(state="disabled")
            self.content_viewer.grid_forget() # Hide it

    def _populate_file_browser(self):
        """Fetches the index of all ever-created files and lists them."""
        # Clear previous file list
        for widget in self.file_browser_frame.winfo_children():
            widget.destroy()

        try:
            file_index = self.controller.get_history_file_index()
            if not file_index:
                ctk.CTkLabel(self.file_browser_frame, text="No configuration history found.").pack(padx=10, pady=10)
                return

            # Sort files alphabetically by name for consistency
            for file_item in sorted(file_index, key=lambda x: x.get('name', '')):
                file_id = file_item.get('id')
                file_name = file_item.get('name', 'Unnamed File')
                if not file_id:
                    logging.warning(f"Skipping file item with no ID: {file_item}")
                    continue

                btn = ctk.CTkButton(self.file_browser_frame, text=file_name,
                                    command=lambda fid=file_id: self._on_file_select(fid))
                btn.pack(fill="x", padx=5, pady=(0, 5)) # Add spacing below each button

        except Exception as e:
            logging.error(f"Error populating file browser: {e}", exc_info=True)
            ctk.CTkLabel(self.file_browser_frame, text="Error loading file list.", text_color="red").pack(padx=10, pady=10)

    def _on_file_select(self, file_id: str):
        """Called when a user clicks a file. Populates the version timeline."""
        logging.debug(f"File selected: {file_id}")
        self._clear_timeline()
        self._clear_content_viewer() # Hide content viewer when a new file is selected

        try:
            version_history = self.controller.get_file_version_history(file_id)
            if not version_history:
                ctk.CTkLabel(self.version_timeline_frame, text="No versions found for this file.").pack(padx=10, pady=10)
                return

            # Display versions, most recent first
            for version in reversed(version_history):
                timestamp = version.get('timestamp')
                action = version.get('action', 'Modified') # Default action if missing
                if not timestamp:
                    logging.warning(f"Skipping version with no timestamp: {version}")
                    continue

                display_text = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({action})"
                btn = ctk.CTkButton(self.version_timeline_frame, text=display_text,
                                    command=lambda fid=file_id, ts=timestamp: self._on_version_select(fid, ts))
                btn.pack(fill="x", padx=5, pady=(0, 5)) # Add spacing

        except Exception as e:
            logging.error(f"Error loading version history for {file_id}: {e}", exc_info=True)
            ctk.CTkLabel(self.version_timeline_frame, text="Error loading versions.", text_color="red").pack(padx=10, pady=10)


    def _on_version_select(self, file_id: str, timestamp):
        """Called when a user clicks a version. Displays its content."""
        logging.info(f"Loading content for file {file_id} at {timestamp}")

        try:
            content = self.controller.get_file_content_at_version(file_id, timestamp)
            content = content or "[No content found for this version]" # Handle empty content

            self.content_viewer.configure(state="normal")
            self.content_viewer.delete("1.0", "end")
            self.content_viewer.insert("1.0", content)
            self.content_viewer.configure(state="disabled")

            # Ensure the content viewer is visible
            self.content_viewer.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="nsew") # Gridded to row 0

        except Exception as e:
            logging.error(f"Error loading content for {file_id} at {timestamp}: {e}", exc_info=True)
            # Display error message in the content viewer itself
            self.content_viewer.configure(state="normal")
            self.content_viewer.delete("1.0", "end")
            self.content_viewer.insert("1.0", f"Error loading content:\n{e}")
            self.content_viewer.configure(state="disabled")
            self.content_viewer.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="nsew")