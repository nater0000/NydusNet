import customtkinter as ctk
import json

class DebugView(ctk.CTkFrame):
    """
    A view for developers to inspect the raw in-memory configuration state.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Left Frame for Object List ---
        self.object_list_frame = ctk.CTkScrollableFrame(self, label_text="Config Objects")
        self.object_list_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ns")

        # --- Right Frame for JSON Display ---
        self.json_display = ctk.CTkTextbox(self, wrap="word", font=("Courier New", 12))
        self.json_display.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

    def enter(self):
        """Called when the view is shown. Populates the object list."""
        # Clear previous widgets
        for widget in self.object_list_frame.winfo_children():
            widget.destroy()

        all_objects = self.controller.get_all_objects_for_debug()

        if not all_objects:
            ctk.CTkLabel(self.object_list_frame, text="No objects in memory.").pack(padx=10, pady=10)
            return

        for obj_id, obj_data in all_objects.items():
            # Determine a display name for the button
            obj_type = obj_data.get('type', 'Unknown')
            name = obj_data.get('hostname') or obj_data.get('name') or obj_id[:8]
            display_text = f"{obj_type.title()}: {name}"

            btn = ctk.CTkButton(
                self.object_list_frame,
                text=display_text,
                command=lambda o=obj_data: self._show_object_details(o)
            )
            btn.pack(fill="x", padx=5, pady=2)

    def _show_object_details(self, obj_data: dict):
        """Displays the formatted JSON for a selected object."""
        self.json_display.delete("1.0", "end")
        pretty_json = json.dumps(obj_data, indent=2)
        self.json_display.insert("1.0", pretty_json)
