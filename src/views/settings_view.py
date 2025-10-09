import customtkinter as ctk
import logging

class SettingsView(ctk.CTkFrame):
    """
    The settings view, providing a tabbed interface for managing servers,
    devices, and application security.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.grid_row_configure(0, weight=1)
        self.grid_column_configure(0, weight=1)

        # --- Create Tabbed Interface ---
        self.tab_view = ctk.CTkTabview(self, anchor="w")
        self.tab_view.grid(row=0, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.tab_view.add("General")
        self.tab_view.add("Servers")
        self.tab_view.add("Devices")
        self.tab_view.add("Security")
        
        # --- Create content for each tab ---
        self._create_general_tab()
        self._create_servers_tab()
        self._create_devices_tab()
        self._create_security_tab()

    def enter(self):
        """Called by the main controller when this view is shown."""
        logging.info("Entering Settings View. Refreshing server and device lists.")
        self._populate_server_list()
        self._populate_device_list()

    def _create_general_tab(self):
        tab = self.tab_view.tab("General")
        back_btn = ctk.CTkButton(tab, text="< Back to Dashboard",
                                 command=lambda: self.controller.show_frame("DashboardView"))
        back_btn.pack(side="top", anchor="w", padx=20, pady=20)
        
        theme_label = ctk.CTkLabel(tab, text="Appearance Mode:")
        theme_label.pack(side="top", anchor="w", padx=20, pady=(10,0))
        theme_menu = ctk.CTkOptionMenu(tab, values=["System", "Light", "Dark"],
                                       command=ctk.set_appearance_mode)
        theme_menu.pack(side="top", anchor="w", padx=20, pady=10)

    def _create_servers_tab(self):
        tab = self.tab_view.tab("Servers")
        add_server_btn = ctk.CTkButton(tab, text="Add New Server",
                                        command=self.controller.add_new_server)
        add_server_btn.pack(side="top", anchor="w", padx=20, pady=20)
        
        self.server_list_frame = ctk.CTkScrollableFrame(tab, label_text="Configured Servers")
        self.server_list_frame.pack(padx=20, pady=10, fill="both", expand=True)

    def _create_devices_tab(self):
        tab = self.tab_view.tab("Devices")
        add_device_btn = ctk.CTkButton(tab, text="Add New Device (Generate Invite)",
                                        command=self.controller.add_new_device)
        add_device_btn.pack(side="top", anchor="w", padx=20, pady=20)
        
        self.device_list_frame = ctk.CTkScrollableFrame(tab, label_text="Synced Devices")
        self.device_list_frame.pack(padx=20, pady=10, fill="both", expand=True)

    def _create_security_tab(self):
        tab = self.tab_view.tab("Security")
        change_password_btn = ctk.CTkButton(tab, text="Change Master Password",
                                             command=self.controller.change_master_password)
        change_password_btn.pack(side="top", anchor="w", padx=20, pady=20)

        view_recovery_key_btn = ctk.CTkButton(tab, text="View Recovery Key",
                                               command=self.controller.view_recovery_key)
        view_recovery_key_btn.pack(side="top", anchor="w", padx=20, pady=10)

    def _populate_server_list(self):
        """Fetches server data and builds the UI list."""
        for widget in self.server_list_frame.winfo_children():
            widget.destroy()

        servers = self.controller.get_servers()
        for server in servers:
            server_frame = ctk.CTkFrame(self.server_list_frame)
            server_frame.pack(fill="x", padx=5, pady=5)
            server_frame.grid_columnconfigure(0, weight=1)

            label = ctk.CTkLabel(server_frame, text=f"{server['name']} ({server['ip_address']})", anchor="w")
            label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

            delete_btn = ctk.CTkButton(server_frame, text="Delete",
                                        command=lambda sid=server['id']: self.controller.delete_server(sid))
            delete_btn.grid(row=0, column=1, padx=10, pady=5)
            
            edit_btn = ctk.CTkButton(server_frame, text="Edit",
                                      command=lambda sid=server['id']: self.controller.edit_server(sid))
            edit_btn.grid(row=0, column=2, padx=10, pady=5)

    def _populate_device_list(self):
        """Fetches client device data and builds the UI list."""
        for widget in self.device_list_frame.winfo_children():
            widget.destroy()

        clients = self.controller.get_clients()
        for client in clients:
            client_frame = ctk.CTkFrame(self.device_list_frame)
            client_frame.pack(fill="x", padx=5, pady=5)
            client_frame.grid_columnconfigure(0, weight=1)

            # You would format the "last_seen" timestamp nicely here
            label = ctk.CTkLabel(client_frame, text=f"{client['name']} (ID: ...{client['syncthing_id'][-12:]}) - Last seen: {client['last_seen']}", anchor="w")
            label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
            
            remove_btn = ctk.CTkButton(client_frame, text="Remove",
                                        command=lambda cid=client['syncthing_id']: self.controller.remove_client(cid))
            remove_btn.grid(row=0, column=1, padx=10, pady=5)
