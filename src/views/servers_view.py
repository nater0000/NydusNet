# views/servers_view.py (New File)
import customtkinter as ctk
import logging
from .dialogs import ToolTip # Import ToolTip

class ServersView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent") # Blend with content area
        self.controller = controller
        # Ensure images are loaded and available from the controller
        self.images = controller.images if hasattr(controller, 'images') else {}
        if not self.images:
            logging.error("ServersView: Images not found in controller!")
        self.tooltips = [] # Initialize list to hold tooltips

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1) # Main column expands
        self.grid_rowconfigure(1, weight=1) # Row 1 (list container) expands vertically

        # --- Top Control Frame ---
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew")

        # Add Server Button (moved to top right)
        ctk.CTkButton(self.control_frame, text="Add Server",
                      image=self.images.get("add"), compound="left",
                      command=self.controller.add_new_server).pack(side="right", padx=5, pady=5)

        # --- Server List Container ---
        self.list_container = ctk.CTkFrame(self, fg_color="transparent")
        self.list_container.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.list_container.grid_rowconfigure(0, weight=1)
        self.list_container.grid_columnconfigure(0, weight=1)

        self.server_list_frame = None # Will be created/recreated in _load_servers_data

    def enter(self):
        """Called every time the view is shown."""
        logging.debug("Entering ServersView.")
        self._load_servers_data()

    def _load_servers_data(self):
        """Loads and displays the list of registered servers."""
        logging.info("Loading and displaying servers.")

        # Destroy old frame and clear tooltips to prevent memory leaks/errors
        if self.server_list_frame is not None and self.server_list_frame.winfo_exists():
            # Explicitly destroy tooltips associated with the old frame first
            for tip in self.tooltips:
                tip.destroy()
            self.tooltips.clear()
            # Now destroy the frame itself
            self.server_list_frame.destroy()

        # Re-create scrollable frame
        self.server_list_frame = ctk.CTkScrollableFrame(self.list_container, label_text="Registered Servers")
        self.server_list_frame.grid(row=0, column=0, sticky="nsew")
        self.server_list_frame.grid_columnconfigure(0, weight=1) # Allow content to expand horizontally

        try:
            servers = self.controller.get_servers()
            if not servers:
                ctk.CTkLabel(self.server_list_frame, text="No servers registered yet. Click 'Add Server' to begin.").pack(pady=20, padx=20)
                return

            # Sort servers alphabetically by name for consistency
            sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))

            for server in sorted_servers:
                # Use a try-except for each server item for resilience
                try:
                    server_id = server.get('id')
                    if not server_id:
                        logging.warning(f"Skipping server item with no ID: {server}")
                        continue

                    is_provisioned = server.get('is_provisioned', False)

                    # Frame for the individual server item
                    item_frame = ctk.CTkFrame(self.server_list_frame)
                    item_frame.pack(fill="x", pady=5, padx=5)
                    # Configure grid columns within the item frame
                    item_frame.grid_columnconfigure(1, weight=1) # Make label column expand

                    # Status Indicator (Left)
                    status_text = "✅ Ready" if is_provisioned else "⚠️ Setup Required"
                    status_color = "green" if is_provisioned else "orange"
                    status_label = ctk.CTkLabel(item_frame, text=status_text, text_color=status_color, width=120, anchor="w") # Fixed width, left align text
                    status_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")

                    # Server Info Label (Middle, Expands)
                    server_name = server.get('name', 'Unnamed Server')
                    ip_address = server.get('ip_address', 'No IP')
                    info_text = f"{server_name} ({ip_address})"
                    info_label = ctk.CTkLabel(item_frame, text=info_text, font=ctk.CTkFont(weight="bold"), anchor="w")
                    info_label.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

                    # Button Frame (Right)
                    btn_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
                    btn_frame.grid(row=0, column=2, padx=(5, 10), pady=5, sticky="e") # Align buttons right
                    btn_width = 30 # For icon-only buttons

                    # Setup Button (only if not provisioned)
                    if not is_provisioned:
                        setup_btn = ctk.CTkButton(btn_frame, text="Setup",
                                                  image=self.images.get("setup"), compound="left",
                                                  width=80,
                                                  command=lambda sid=server_id: self.controller.provision_server(sid))
                        setup_btn.pack(side="left", padx=3)
                        self.tooltips.append(ToolTip(setup_btn, f"Run Setup for {server_name}"))

                    # Edit Button
                    edit_btn = ctk.CTkButton(btn_frame, text="", width=btn_width,
                                               image=self.images.get("edit"),
                                               command=lambda sid=server_id: self.controller.edit_server(sid))
                    edit_btn.pack(side="left", padx=3)
                    self.tooltips.append(ToolTip(edit_btn, f"Edit {server_name}"))

                    # Delete Button
                    delete_btn = ctk.CTkButton(btn_frame, text="", width=btn_width,
                                                 image=self.images.get("delete"),
                                                 fg_color="#D32F2F", hover_color="#B71C1C", # Standard delete colors
                                                 command=lambda sid=server_id: self.controller.delete_server(sid))
                    delete_btn.pack(side="left", padx=3)
                    self.tooltips.append(ToolTip(delete_btn, f"Delete {server_name}"))

                except Exception as e:
                    logging.error(f"Error creating server widget for ID {server.get('id', 'UNKNOWN')}: {e}", exc_info=True)
                    # Display error within the list if frame exists
                    if self.server_list_frame.winfo_exists():
                         error_label = ctk.CTkLabel(self.server_list_frame, text=f"Error loading server {server.get('id', 'UNKNOWN')}", text_color="red")
                         error_label.pack(fill="x", pady=5, padx=5)

        except Exception as e:
            logging.error(f"Critical error during _load_servers_data: {e}", exc_info=True)
            # Display general error if frame exists
            if self.server_list_frame and self.server_list_frame.winfo_exists():
                 ctk.CTkLabel(self.server_list_frame, text="An error occurred loading servers. Check logs.", text_color="red").pack(padx=20, pady=20)
                 