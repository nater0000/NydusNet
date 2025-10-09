import customtkinter as ctk
import logging

class HistoryView(ctk.CTkFrame):
    """
    The history view, allowing users to browse the version history of
    configuration files.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.grid_columnconfigure(2, weight=1) # Right-most column expands
        self.grid_row_configure(1, weight=1)

        # --- Top Control Bar ---
        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 0), sticky="ew")

        back_btn = ctk.CTkButton(top_frame, text="< Back to Dashboard",
                                 command=lambda: self.controller.show_frame("DashboardView"))
        back_btn.pack(side="left", padx=10, pady=10)

        # --- Panes ---
        self.file_browser_frame = ctk.CTkScrollableFrame(self, label_text="Configuration Files")
        self.file_browser_frame.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="nsew")

        self.version_timeline_frame = ctk.CTkScrollableFrame(self, label_text="File History")
        self.version_timeline_frame.grid(row=1, column=1, padx=5, pady=10, sticky="nsew")

        self.content_viewer = ctk.CTkTextbox(self, state="disabled", wrap="none") # Read-only, no line wrapping

    def enter(self):
        """Called by the main controller when this view is shown to refresh data."""
        logging.info("Entering History View.")
        self._populate_file_browser()
        # Clear other panes when entering
        self._clear_timeline()
        self._clear_content_viewer()

    def _clear_timeline(self):
        for widget in self.version_timeline_frame.winfo_children():
            widget.destroy()

    def _clear_content_viewer(self):
        self.content_viewer.configure(state="normal")
        self.content_viewer.delete("1.0", "end")
        self.content_viewer.configure(state="disabled")

    def _populate_file_browser(self):
        """Fetches the index of all ever-created files and lists them."""
        self._clear_timeline()
        for widget in self.file_browser_frame.winfo_children():
            widget.destroy()

        file_index = self.controller.get_history_file_index()
        if not file_index:
            ctk.CTkLabel(self.file_browser_frame, text="No history found.").pack(padx=10, pady=10)
            return

        for file_item in sorted(file_index, key=lambda x: x['name']):
            file_id = file_item['id']
            file_name = file_item['name']
            
            btn = ctk.CTkButton(self.file_browser_frame, text=file_name,
                                command=lambda fid=file_id: self._on_file_select(fid))
            btn.pack(fill="x", padx=5, pady=5)

    def _on_file_select(self, file_id: str):
        """Called when a user clicks a file. Populates the version timeline."""
        self._clear_timeline()
        self._clear_content_viewer()

        version_history = self.controller.get_file_version_history(file_id)
        if not version_history:
            ctk.CTkLabel(self.version_timeline_frame, text="No versions found.").pack(padx=10, pady=10)
            return
        
        for version in reversed(version_history): # Show most recent first
            timestamp = version['timestamp']
            action = version['action']
            
            display_text = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({action})"
            btn = ctk.CTkButton(self.version_timeline_frame, text=display_text,
                                command=lambda fid=file_id, ts=timestamp: self._on_version_select(fid, ts))
            btn.pack(fill="x", padx=5, pady=5)

    def _on_version_select(self, file_id: str, timestamp):
        """Called when a user clicks a version. Displays its content."""
        logging.info(f"Loading content for file {file_id} at {timestamp}")
        
        content = self.controller.get_file_content_at_version(file_id, timestamp)

        self.content_viewer.configure(state="normal")
        self.content_viewer.delete("1.0", "end")
        self.content_viewer.insert("1.0", content)
        self.content_viewer.configure(state="disabled")
        
        # Ensure the content viewer is visible if it wasn't before
        self.content_viewer.grid(row=1, column=2, padx=(5, 10), pady=10, sticky="nsew")
