import customtkinter as ctk
import logging
from .dialogs import ToolTip

class DashboardView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent") # Blend with content_frame
        self.controller = controller
        self.tooltips = []
        # Ensure images are loaded and available from the controller
        self.images = controller.images if hasattr(controller, 'images') else {} 
        if not self.images:
            logging.error("DashboardView: Images not found in controller!")

        # --- FIX: Add a flag to prevent race conditions ---
        self.is_loading = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1) # Row 1 for the list

        # --- Top Control Frame (now just for actions) ---
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew")

        ctk.CTkButton(self.control_frame, text="Start All",
                      image=self.images.get("start_all"), compound="left",
                      command=self.controller.start_all_tunnels).pack(side="left", padx=5, pady=5)

        ctk.CTkButton(self.control_frame, text="Stop All",
                      image=self.images.get("stop_all"), compound="left",
                      command=self._on_stop_all_clicked).pack(side="left", padx=5, pady=5)

        ctk.CTkButton(self.control_frame, text="Add Tunnel",
                      image=self.images.get("add"), compound="left",
                      command=self.controller.add_new_tunnel).pack(side="right", padx=5, pady=5)

        # --- (Navigation buttons removed) ---

        # --- A container for the list that will be recreated ---
        self.list_container = ctk.CTkFrame(self, fg_color="transparent")
        self.list_container.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.list_container.grid_rowconfigure(0, weight=1)
        self.list_container.grid_columnconfigure(0, weight=1)

        self.tunnel_list_frame = None # Will be created/recreated in load_tunnels

    def enter(self):
        """Called when the view becomes visible."""
        self.load_tunnels()

    def _on_stop_all_clicked(self):
        """Handles the 'Stop All' button click."""
        self.controller.stop_all_tunnels()
        # Refresh dashboard immediately after stopping all
        self.controller.after(50, self.controller.refresh_dashboard) # Slight delay

    def load_tunnels(self):
        """Loads and displays the list of tunnels, preventing concurrent loads."""
        # --- FIX: Check the flag ---
        if self.is_loading:
            logging.warning("Dashboard refresh already in progress. Skipping.")
            return

        # --- FIX: Set the flag ---
        self.is_loading = True

        logging.info("Loading and displaying tunnels on the dashboard.")

        try:
            # Destroy the entire old frame to prevent widget conflicts
            if self.tunnel_list_frame is not None and self.tunnel_list_frame.winfo_exists():
                self.tunnel_list_frame.destroy()

            # Clear the list of active tooltips
            self.tooltips.clear()

            # Re-create a fresh scrollable frame within the container
            self.tunnel_list_frame = ctk.CTkScrollableFrame(self.list_container, label_text="Tunnels")
            self.tunnel_list_frame.grid(row=0, column=0, sticky="nsew")
            self.tunnel_list_frame.grid_columnconfigure(0, weight=1) # Allow items to fill width

            # Fetch current data
            tunnels = self.controller.get_tunnels()
            tunnel_statuses = self.controller.get_tunnel_statuses()
            my_device_id = self.controller.get_my_device_id() # May be None initially

            if not tunnels:
                ctk.CTkLabel(self.tunnel_list_frame, text="No tunnels configured yet. Click 'Add Tunnel' to create one.").pack(padx=20, pady=20)
                # No 'return' needed here, finally block will run
            else:
                for tunnel in tunnels:
                    # Use a try-except block for each tunnel item for resilience
                    try:
                        tunnel_id = tunnel['id']
                        status = tunnel_statuses.get(tunnel_id, "stopped") # Default to stopped
                        status_color = {"running": "#2ECC71", "connecting": "#F39C12", "stopped": "gray50", "error": "#E74C3C"}.get(status, "gray50")

                        assigned_client_id = tunnel.get('assigned_client_id')
                        is_managed_by_me = my_device_id and (assigned_client_id == my_device_id)
                        is_unassigned = not assigned_client_id

                        # Create the frame for this tunnel item
                        item_frame = ctk.CTkFrame(self.tunnel_list_frame)
                        item_frame.pack(fill="x", pady=5, padx=5)
                        item_frame.grid_columnconfigure(1, weight=1) # Info label column expands

                        # Status indicator (dot)
                        status_indicator = ctk.CTkLabel(item_frame, text="●", text_color=status_color, font=("", 30))
                        status_indicator.grid(row=0, column=0, rowspan=2, padx=(10, 15), pady=5, sticky="ns")
                        self.tooltips.append(ToolTip(status_indicator, f"Status: {status.capitalize()}"))

                        # Main info label (Hostname -> Destination via Server)
                        server_name = self.controller.get_server_name(tunnel.get('server_id', '')) or "Unknown Server"
                        info_text = f"{tunnel.get('hostname','N/A')} → {tunnel.get('local_destination','N/A')} (via {server_name})"
                        info_label = ctk.CTkLabel(item_frame, text=info_text, anchor="w", font=ctk.CTkFont(size=14, weight="bold"))
                        info_label.grid(row=0, column=1, sticky="ew", padx=5, pady=(5,0))

                        # Managed by label
                        assigned_client_name = self.controller.get_client_name(assigned_client_id) or "Any Device"
                        manager_text = f"Managed by: {assigned_client_name}"
                        manager_label = ctk.CTkLabel(item_frame, text=manager_text, anchor="w", text_color="gray60")
                        manager_label.grid(row=1, column=1, sticky="ew", padx=5, pady=(0,5))

                        # Frame for action buttons on the right
                        button_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
                        button_frame.grid(row=0, column=2, rowspan=2, padx=10, sticky="ns")

                        # Determine button state (enabled only if managed by this device or unassigned)
                        btn_state = "normal" if (is_managed_by_me or is_unassigned) else "disabled"
                        btn_width = 30 # Standard width for icon buttons

                        # Start/Stop Button
                        if status in ['running', 'connecting']:
                            start_stop_btn = ctk.CTkButton(button_frame, text="", width=btn_width,
                                                           image=self.images.get("stop"),
                                                           command=lambda tid=tunnel_id: self.controller.stop_tunnel(tid),
                                                           state=btn_state)
                            self.tooltips.append(ToolTip(start_stop_btn, "Stop Tunnel"))
                        else:
                            start_stop_btn = ctk.CTkButton(button_frame, text="", width=btn_width,
                                                           image=self.images.get("start"),
                                                           command=lambda tid=tunnel_id: self.controller.start_tunnel(tid),
                                                           state=btn_state)
                            self.tooltips.append(ToolTip(start_stop_btn, "Start Tunnel"))
                        start_stop_btn.pack(side="left", padx=3)

                        # Edit Button (always enabled)
                        edit_btn = ctk.CTkButton(button_frame, text="", width=btn_width,
                                                 image=self.images.get("edit"),
                                                 command=lambda tid=tunnel_id: self.controller.edit_tunnel(tid))
                        edit_btn.pack(side="left", padx=3)
                        self.tooltips.append(ToolTip(edit_btn, "Edit Tunnel"))

                        # Logs Button (always enabled)
                        logs_btn = ctk.CTkButton(button_frame, text="", width=btn_width,
                                                 image=self.images.get("logs"),
                                                 command=lambda tid=tunnel_id: self.controller.view_tunnel_log(tid))
                        logs_btn.pack(side="left", padx=3)
                        self.tooltips.append(ToolTip(logs_btn, "View Logs"))

                        # Delete Button (always enabled)
                        delete_btn = ctk.CTkButton(button_frame, text="", width=btn_width,
                                                   image=self.images.get("delete"),
                                                   fg_color="#D32F2F", hover_color="#B71C1C", # Standard delete colors
                                                   command=lambda tid=tunnel_id: self.controller.delete_tunnel(tid))
                        delete_btn.pack(side="left", padx=3)
                        self.tooltips.append(ToolTip(delete_btn, "Delete Tunnel"))

                    except Exception as e:
                        # Log error for the specific tunnel item but continue loading others
                        logging.error(f"Error creating tunnel widget for ID {tunnel.get('id', 'UNKNOWN')}: {e}", exc_info=True)
                        # Display an error message within the list if the frame still exists
                        if self.tunnel_list_frame.winfo_exists():
                            error_label = ctk.CTkLabel(self.tunnel_list_frame, text=f"Error loading tunnel {tunnel.get('id', 'UNKNOWN')}", text_color="red")
                            error_label.pack(fill="x", pady=5, padx=5)

        except Exception as e:
             # Log any unexpected error during the whole load process
            logging.error(f"Critical error during load_tunnels: {e}", exc_info=True)
            # Optionally display a general error message if the frame exists
            if self.tunnel_list_frame and self.tunnel_list_frame.winfo_exists():
                 ctk.CTkLabel(self.tunnel_list_frame, text="An error occurred loading tunnels. Check logs.", text_color="red").pack(padx=20, pady=20)

        finally:
            # --- FIX: ALWAYS reset the flag when done, regardless of errors ---
            self.is_loading = False
            logging.debug("Finished loading tunnels. is_loading set to False.")