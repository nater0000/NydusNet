import customtkinter as ctk
import logging
from .dialogs import ToolTip 

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
        
        # --- EMOJI / ICON BUTTONS with Tooltips for a cleaner look ---
        self.start_all_btn = ctk.CTkButton(self.control_frame, text="▶️ Start All", command=self.controller.start_all_tunnels)
        self.start_all_btn.pack(side="left", padx=5, pady=5)
        
        self.stop_all_btn = ctk.CTkButton(self.control_frame, text="⏹️ Stop All", command=self._on_stop_all_clicked)
        self.stop_all_btn.pack(side="left", padx=5, pady=5)
        
        self.add_tunnel_btn = ctk.CTkButton(self.control_frame, text="➕ Add Tunnel", command=self.controller.add_new_tunnel)
        self.add_tunnel_btn.pack(side="left", padx=5, pady=5)

        # Navigation buttons
        self.debug_btn = ctk.CTkButton(self.control_frame, text="🐞 Debug",
                                         command=lambda: self.controller.show_frame("DebugView"))
        self.debug_btn.pack(side="right", padx=5, pady=5)
        
        self.history_btn = ctk.CTkButton(self.control_frame, text="📜 History",
                                         command=lambda: self.controller.show_frame("HistoryView"))
        self.history_btn.pack(side="right", padx=5, pady=5)

        self.settings_btn = ctk.CTkButton(self.control_frame, text="⚙️ Settings",
                                          command=lambda: self.controller.show_frame("SettingsView"))
        self.settings_btn.pack(side="right", padx=5, pady=5)
        
        # --- Tunnel List Frame ---
        self.tunnel_list_frame = ctk.CTkScrollableFrame(self, label_text="Tunnels")
        self.tunnel_list_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.tunnel_list_frame.grid_columnconfigure(1, weight=1)
        self.tooltips = [] # To hold tooltip objects

    def enter(self):
        """Called by the main controller whenever this view is shown."""
        self.load_tunnels()

    def _on_stop_all_clicked(self):
        """Called when the 'Stop All' button is clicked to sequence actions."""
        self.controller.stop_all_tunnels()
        self.controller.refresh_dashboard()
        
    def load_tunnels(self):
        """
        Loads tunnel data from the config manager and populates the list.
        """
        logging.info("Loading and displaying tunnels on the dashboard.")
        
        # Clear previous widgets and tooltips
        for widget in self.tunnel_list_frame.winfo_children():
            widget.destroy()
        self.tooltips.clear()

        tunnels = self.controller.get_tunnels()
        tunnel_statuses = self.controller.get_tunnel_statuses()
        my_device_id = self.controller.get_my_device_id()

        if not tunnels:
            no_tunnels_label = ctk.CTkLabel(self.tunnel_list_frame, text="No tunnels configured. Click 'Add New Tunnel' to get started.")
            no_tunnels_label.pack(padx=20, pady=20)
            return

        for i, tunnel in enumerate(tunnels):
            tunnel_id = tunnel['id']
            status = tunnel_statuses.get(tunnel_id, "stopped")
            status_color = {"running": "green", "stopped": "gray", "error": "red"}.get(status, "gray")
            
            # --- Main Info Frame ---
            info_frame = ctk.CTkFrame(self.tunnel_list_frame)
            info_frame.grid(row=i, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
            info_frame.grid_columnconfigure(1, weight=1)

            status_indicator = ctk.CTkLabel(info_frame, text="●", text_color=status_color, font=("", 24))
            status_indicator.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=5)
            
            server_name = self.controller.get_server_name(tunnel.get('server_id'))
            info_text = f"{tunnel['hostname']}  ->  {tunnel['local_destination']}  (on {server_name})"
            info_label = ctk.CTkLabel(info_frame, text=info_text, anchor="w")
            info_label.grid(row=0, column=1, padx=10, pady=(5,0), sticky="ew")

            # --- Managed By Label ---
            assigned_client_id = tunnel.get('assigned_client_id')
            client_name = self.controller.get_client_name(assigned_client_id)
            managed_by_text = f"Managed by: {client_name or 'ANY DEVICE'}"
            managed_by_label = ctk.CTkLabel(info_frame, text=managed_by_text, text_color="gray", font=("", 10), anchor="w")
            managed_by_label.grid(row=1, column=1, padx=10, pady=(0,5), sticky="ew")
            
            # --- Control Buttons Frame ---
            button_frame = ctk.CTkFrame(self.tunnel_list_frame)
            button_frame.grid(row=i, column=2, padx=10, pady=5, sticky="e")
            
            is_assigned_to_this_device = (assigned_client_id is None or assigned_client_id == my_device_id)
            button_state = "normal" if is_assigned_to_this_device else "disabled"

            # --- Icon Buttons with Text Fallback and Tooltips ---
            if status == 'running':
                start_stop_btn = ctk.CTkButton(button_frame, text="⏹️", width=30, command=lambda tid=tunnel_id: self.controller.stop_tunnel(tid), state=button_state)
                self.tooltips.append(ToolTip(start_stop_btn, "Stop Tunnel"))
            else:
                start_stop_btn = ctk.CTkButton(button_frame, text="▶️", width=30, command=lambda tid=tunnel_id: self.controller.start_tunnel(tid), state=button_state)
                self.tooltips.append(ToolTip(start_stop_btn, "Start Tunnel"))
            start_stop_btn.pack(side="left", padx=5)

            edit_btn = ctk.CTkButton(button_frame, text="✏️", width=30, command=lambda tid=tunnel_id: self.controller.edit_tunnel(tid))
            self.tooltips.append(ToolTip(edit_btn, "Edit Tunnel"))
            edit_btn.pack(side="left", padx=5)
            
            logs_btn = ctk.CTkButton(button_frame, text="📄", width=30, command=lambda tid=tunnel_id: self.controller.view_tunnel_log(tid))
            self.tooltips.append(ToolTip(logs_btn, "View Logs"))
            logs_btn.pack(side="left", padx=5)
            
            delete_btn = ctk.CTkButton(button_frame, text="🗑️", width=30, fg_color="red", hover_color="#C00000", command=lambda tid=tunnel_id: self.controller.delete_tunnel(tid))
            self.tooltips.append(ToolTip(delete_btn, "Delete Tunnel"))
            delete_btn.pack(side="left", padx=5)

