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

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Create Tabbed Interface ---
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        self.tab_view.add("General")
        self.tab_view.add("Servers")
        self.tab_view.add("Devices")
        self.tab_view.add("Security")
        
        # --- Populate General Tab ---
        self.general_tab = self.tab_view.tab("General")
        self.back_to_dashboard_btn = ctk.CTkButton(self.general_tab, text="Back to Dashboard",
                                                   command=lambda: controller.show_frame("DashboardView"))
        self.back_to_dashboard_btn.pack(padx=20, pady=20)
        
        # You could add other general settings here, like theme selection
        self.theme_label = ctk.CTkLabel(self.general_tab, text="Appearance Mode:")
        self.theme_label.pack(padx=20, pady=(10,0))
        self.theme_menu = ctk.CTkOptionMenu(self.general_tab, values=["System", "Light", "Dark"],
                                            command=ctk.set_appearance_mode)
        self.theme_menu.pack(padx=20, pady=10)


        # --- Populate Servers Tab ---
        self.servers_tab = self.tab_view.tab("Servers")
        # In a real app, this list would be built dynamically
        self.add_server_btn = ctk.CTkButton(self.servers_tab, text="Add New Server")
        self.add_server_btn.pack(padx=20, pady=20)
        
        server_list_frame = ctk.CTkScrollableFrame(self.servers_tab, label_text="Configured Servers")
        server_list_frame.pack(padx=20, pady=10, fill="both", expand=True)
        # Placeholder for server list
        ctk.CTkLabel(server_list_frame, text="My IONOS VPS (74.208.126.76)").pack(anchor="w", padx=10)


        # --- Populate Devices Tab ---
        self.devices_tab = self.tab_view.tab("Devices")
        self.add_device_btn = ctk.CTkButton(self.devices_tab, text="Add New Device (Generate Invite)")
        self.add_device_btn.pack(padx=20, pady=20)
        
        device_list_frame = ctk.CTkScrollableFrame(self.devices_tab, label_text="Synced Devices")
        device_list_frame.pack(padx=20, pady=10, fill="both", expand=True)
        # Placeholder for device list
        ctk.CTkLabel(device_list_frame, text="Home Desktop (AAAA-BBBB...) - Last seen: 2 minutes ago").pack(anchor="w", padx=10)
        ctk.CTkLabel(device_list_frame, text="Work Laptop (DDDD-EEEE...) - Last seen: 3 hours ago").pack(anchor="w", padx=10)


        # --- Populate Security Tab ---
        self.security_tab = self.tab_view.tab("Security")
        self.change_password_btn = ctk.CTkButton(self.security_tab, text="Change Master Password")
        self.change_password_btn.pack(padx=20, pady=20)

        self.view_recovery_key_btn = ctk.CTkButton(self.security_tab, text="View Recovery Key")
        self.view_recovery_key_btn.pack(padx=20, pady=10)
