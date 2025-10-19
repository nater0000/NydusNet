import customtkinter as ctk
import logging

class SettingsView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Back Button ---
        back_btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        back_btn_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(back_btn_frame, text="← Back to Dashboard", command=lambda: self.controller.show_frame("DashboardView")).pack(side="left")

        # --- Tabbed Interface ---
        self.tab_view = ctk.CTkTabview(self, anchor="w")
        self.tab_view.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.tab_view.add("Servers")
        self.tab_view.add("Devices")
        self.tab_view.add("Security")
        self.tab_view.add("General")
        self.tab_view.set("Servers") # Default to the most used tab

        # Create the static content (widgets) for each tab just once
        self._create_servers_tab()
        self._create_devices_tab()
        self._create_security_tab()
        self._create_general_tab()

    def enter(self):
        """Called every time the view is shown to refresh all dynamic data."""
        logging.debug("Entering SettingsView, reloading all data.")
        self._load_servers_data()
        self._load_devices_data()
        self._load_security_data()

    # --- Servers Tab (With Provisioning) ---
    def _create_servers_tab(self):
        tab = self.tab_view.tab("Servers")
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(1, weight=1)
        ctk.CTkButton(tab, text="➕ Register New Server", command=self.controller.add_new_server).pack(pady=10)
        self.server_list_frame = ctk.CTkScrollableFrame(tab, label_text="Registered Servers")
        self.server_list_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def _load_servers_data(self):
        for widget in self.server_list_frame.winfo_children():
            widget.destroy()

        servers = self.controller.get_servers()
        if not servers:
            ctk.CTkLabel(self.server_list_frame, text="No servers registered.").pack(pady=20)
            return

        for server in servers:
            server_id = server['id']
            is_provisioned = server.get('is_provisioned', False)
            
            item_frame = ctk.CTkFrame(self.server_list_frame)
            item_frame.pack(fill="x", pady=5)
            item_frame.grid_columnconfigure(1, weight=1)

            status_text = "✅ Ready" if is_provisioned else "⚠️ Setup Required"
            status_color = "green" if is_provisioned else "orange"
            ctk.CTkLabel(item_frame, text=status_text, text_color=status_color).grid(row=0, column=0, padx=10)

            info_text = f"{server['name']} ({server['ip_address']})"
            ctk.CTkLabel(item_frame, text=info_text, font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w")

            btn_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            btn_frame.grid(row=0, column=2, padx=10, pady=5)

            if not is_provisioned:
                setup_btn = ctk.CTkButton(btn_frame, text="Setup Now...", command=lambda sid=server_id: self.controller.provision_server(sid))
                setup_btn.pack(side="left", padx=5)
            
            edit_btn = ctk.CTkButton(btn_frame, text="Edit", width=60, command=lambda sid=server_id: self.controller.edit_server(sid))
            edit_btn.pack(side="left", padx=5)

            delete_btn = ctk.CTkButton(btn_frame, text="Delete", width=60, fg_color="red", command=lambda sid=server_id: self.controller.delete_server(sid))
            delete_btn.pack(side="left", padx=5)

    # --- Devices Tab ---
    def _create_devices_tab(self):
        tab = self.tab_view.tab("Devices")
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(2, weight=1)
        this_device_frame = ctk.CTkFrame(tab)
        this_device_frame.pack(fill="x", padx=10, pady=10)
        self.this_device_name_label = ctk.CTkLabel(this_device_frame, text="This Device: ...", font=ctk.CTkFont(weight="bold"))
        self.this_device_name_label.pack(anchor="w", padx=10, pady=(10,0))
        self.this_device_id_label = ctk.CTkLabel(this_device_frame, text="ID: ...", wraplength=500, justify="left")
        self.this_device_id_label.pack(anchor="w", padx=10, pady=(0,10))
        ctk.CTkButton(tab, text="➕ Invite Another Device", command=self.controller.add_new_device).pack(pady=10)
        self.other_devices_frame = ctk.CTkScrollableFrame(tab, label_text="Other Synced Devices")
        self.other_devices_frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    def _load_devices_data(self):
        self.this_device_name_label.configure(text=f"This Device: {self.controller.get_my_device_name()}")
        self.this_device_id_label.configure(text=f"ID: {self.controller.get_my_device_id() or 'Initializing...'}")
        for widget in self.other_devices_frame.winfo_children(): widget.destroy()
        clients = self.controller.get_clients()
        if not clients: 
            ctk.CTkLabel(self.other_devices_frame, text="No other devices have been added.").pack(pady=20)
            return
        for client in clients:
            client_id = client.get('syncthing_id', 'Unknown ID')
            client_name = client.get('name', 'Unnamed Device')
            item_frame = ctk.CTkFrame(self.other_devices_frame); item_frame.pack(fill="x", pady=5)
            ctk.CTkLabel(item_frame, text=f"{client_name}\n{client_id}", justify="left").pack(side="left", padx=10, pady=5)
            ctk.CTkButton(item_frame, text="Remove", fg_color="red", command=lambda cid=client_id: self.controller.remove_client(cid)).pack(side="right", padx=10, pady=5)

    # --- Security Tab ---
    def _create_security_tab(self):
        tab = self.tab_view.tab("Security")
        tab.grid_columnconfigure(1, weight=1)
        ssh_frame = ctk.CTkFrame(tab); ssh_frame.pack(fill="x", padx=10, pady=10)
        ssh_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ssh_frame, text="SSH Automation Settings", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, padx=10, pady=10)
        ctk.CTkLabel(ssh_frame, text="Private Key:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.priv_key_entry = ctk.CTkEntry(ssh_frame); self.priv_key_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkButton(ssh_frame, text="Browse...", width=80, command=self._browse_private_key).grid(row=1, column=2, padx=10, pady=5)
        ctk.CTkLabel(ssh_frame, text="Public Key:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.pub_key_entry = ctk.CTkEntry(ssh_frame); self.pub_key_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkButton(ssh_frame, text="Browse...", width=80, command=self._browse_public_key).grid(row=2, column=2, padx=10, pady=5)
        ctk.CTkButton(ssh_frame, text="Save SSH Keys", command=self._save_ssh_keys).grid(row=3, column=0, columnspan=3, pady=10)
        
        pass_frame = ctk.CTkFrame(tab); pass_frame.pack(fill="x", padx=10, pady=10, expand=True)
        ctk.CTkLabel(pass_frame, text="Password Management", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        ctk.CTkButton(pass_frame, text="Change Master Password...", command=self.controller.change_master_password).pack(pady=5)
        ctk.CTkButton(pass_frame, text="View Recovery Key...", command=self.controller.view_recovery_key).pack(pady=5)
    
    def _load_security_data(self):
        creds = self.controller.get_automation_credentials()
        self.priv_key_entry.delete(0, "end"); self.pub_key_entry.delete(0, "end")
        if creds:
            self.priv_key_entry.insert(0, creds.get('ssh_private_key_path', ''))
            self.pub_key_entry.insert(0, creds.get('ssh_public_key_path', ''))
    
    def _browse_private_key(self):
        path = self.controller.browse_for_file("Select Private Key");
        if path: self.priv_key_entry.delete(0, "end"); self.priv_key_entry.insert(0, path)
    
    def _browse_public_key(self):
        path = self.controller.browse_for_file("Select Public Key")
        if path: self.pub_key_entry.delete(0, "end"); self.pub_key_entry.insert(0, path)
            
    def _save_ssh_keys(self):
        priv_path = self.priv_key_entry.get(); pub_path = self.pub_key_entry.get()
        if not priv_path: self.controller.show_error("Private key path cannot be empty."); return
        self.controller.save_or_update_automation_credentials(priv_path, pub_path)
        confirm_label = ctk.CTkLabel(self.tab_view.tab("Security"), text="✓ SSH keys saved!", text_color="green")
        confirm_label.pack(pady=(0, 10)); confirm_label.after(3000, confirm_label.destroy)

    # --- General Tab ---
    def _create_general_tab(self):
        tab = self.tab_view.tab("General")
        appearance_frame = ctk.CTkFrame(tab)
        appearance_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(appearance_frame, text="Appearance Mode:").pack(side="left", padx=10, pady=10)
        self.appearance_menu = ctk.CTkOptionMenu(appearance_frame, values=["Light", "Dark", "System"], command=self.controller.set_appearance_mode)
        self.appearance_menu.pack(side="left", padx=10, pady=10)
        self.appearance_menu.set(ctk.get_appearance_mode())

