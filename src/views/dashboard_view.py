import customtkinter as ctk
import logging

class DashboardView(ctk.CTkFrame):
    """
    The main view of the application, displaying the list of tunnels and global controls.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Top Control Frame ---
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew")

        self.start_all_btn = ctk.CTkButton(self.control_frame, text="Start All Tunnels", command=self.controller.start_all_tunnels)
        self.start_all_btn.pack(side="left", padx=5, pady=5)
        
        self.stop_all_btn = ctk.CTkButton(self.control_frame, text="Stop All Tunnels", command=self.controller.stop_all_tunnels)
        self.stop_all_btn.pack(side="left", padx=5, pady=5)
        
        self.add_tunnel_btn = ctk.CTkButton(self.control_frame, text="Add New Tunnel", command=self.controller.add_new_tunnel)
        self.add_tunnel_btn.pack(side="left", padx=5, pady=5)

        # Navigation buttons
        self.history_btn = ctk.CTkButton(self.control_frame, text="View History",
                                         command=lambda: self.controller.show_frame("HistoryView"))
        self.history_btn.pack(side="right", padx=5, pady=5)

        self.settings_btn = ctk.CTkButton(self.control_frame, text="Settings",
                                          command=lambda: self.controller.show_frame("SettingsView"))
        self.settings_btn.pack(side="right", padx=5, pady=5)
        
        # --- Tunnel List Frame ---
        self.tunnel_list_frame = ctk.CTkScrollableFrame(self, label_text="Tunnels")
        self.tunnel_list_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.tunnel_list_frame.grid_columnconfigure(1, weight=1)

        # --- Load and Display Tunnels ---
        self.load_tunnels()
        
    def load_tunnels(self):
        """
        Loads tunnel data from the config manager and populates the list.
        This method will be called to refresh the UI.
        """
        logging.info("Loading and displaying tunnels on the dashboard.")
        
        # Clear any existing widgets in the scrollable frame first
        for widget in self.tunnel_list_frame.winfo_children():
            widget.destroy()

        # Get real tunnel data from the controller
        tunnels = self.controller.get_tunnels()
        
        # Get live status from the tunnel manager
        tunnel_statuses = self.controller.get_tunnel_statuses()

        if not tunnels:
            no_tunnels_label = ctk.CTkLabel(self.tunnel_list_frame, text="No tunnels configured. Click 'Add New Tunnel' to get started.")
            no_tunnels_label.pack(padx=20, pady=20)
            return

        for i, tunnel in enumerate(tunnels):
            tunnel_id = tunnel['id']
            status = tunnel_statuses.get(tunnel_id, "stopped") # Default to "stopped" if not found
            status_color = {"running": "green", "stopped": "gray", "error": "red"}.get(status, "gray")
            
            # Status Indicator
            status_indicator = ctk.CTkLabel(self.tunnel_list_frame, text="●", text_color=status_color, font=("", 24))
            status_indicator.grid(row=i, column=0, padx=10, pady=5)
            
            # Tunnel Info Label
            # Here you would also get server name from config manager
            server_name = self.controller.get_server_name(tunnel['server_id'])
            info_text = f"{tunnel['hostname']}  ->  {tunnel['local_destination']}  (on {server_name})"
            info_label = ctk.CTkLabel(self.tunnel_list_frame, text=info_text, anchor="w")
            info_label.grid(row=i, column=1, padx=10, pady=5, sticky="ew")

            # Individual Start/Stop/Edit Buttons
            button_frame = ctk.CTkFrame(self.tunnel_list_frame)
            button_frame.grid(row=i, column=2, padx=10, pady=5)
            
            if status == 'running':
                start_stop_btn = ctk.CTkButton(button_frame, text="Stop", command=lambda tid=tunnel_id: self.controller.stop_tunnel(tid))
            else:
                start_stop_btn = ctk.CTkButton(button_frame, text="Start", command=lambda tid=tunnel_id: self.controller.start_tunnel(tid))
            start_stop_btn.pack(side="left", padx=5)

            edit_btn = ctk.CTkButton(button_frame, text="Edit", command=lambda tid=tunnel_id: self.controller.edit_tunnel(tid))
            edit_btn.pack(side="left", padx=5)
