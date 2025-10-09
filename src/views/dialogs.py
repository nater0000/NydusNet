import customtkinter as ctk
import qrcode
from PIL import Image, ImageTk
import logging

class BaseDialog(ctk.CTkToplevel):
    """A base class for all modal dialogs in the application."""
    def __init__(self, parent, title="Dialog"):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self._parent = parent

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # Center the dialog on the parent window after a short delay
        self.after(50, self._center_window)
        
    def _center_window(self):
        self._parent.update_idletasks()
        parent_x = self._parent.winfo_x()
        parent_y = self._parent.winfo_y()
        parent_width = self._parent.winfo_width()
        parent_height = self._parent.winfo_height()
        
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        self.geometry(f"+{x}+{y}")

    def _on_ok(self, event=None):
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()

    def get_input(self):
        # This makes the dialog wait until it's closed before returning a value
        self.wait_window()
        return self.result

class UnlockDialog(BaseDialog):
    """
    Dialog to get the master password.
    Supports both unlock and first-time password creation modes.
    """
    def __init__(self, parent, first_run: bool = False, controller=None):
        title = "Create Master Password" if first_run else "Unlock NydusNet"
        super().__init__(parent, title=title)
        self.controller = controller

        message = "Enter a new master password:" if first_run else "Enter Master Password:"
        self.label = ctk.CTkLabel(self, text=message)
        self.label.pack(padx=20, pady=(20, 10))

        self.entry = ctk.CTkEntry(self, show="*", width=250)
        self.entry.pack(padx=20, pady=10)
        self.entry.bind("<Return>", self._on_ok)
        self.entry.focus_set()

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=(10, 20))
        
        ok_button_text = "Create" if first_run else "Unlock"
        ok_button = ctk.CTkButton(button_frame, text=ok_button_text, command=self._on_ok)
        ok_button.pack(side="left", padx=10)
        
        if not first_run and self.controller:
            forgot_button = ctk.CTkButton(button_frame, text="Forgot Password?", command=self._on_forgot)
            forgot_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        self.result = self.entry.get()
        super()._on_ok()

    def _on_forgot(self):
        self.result = None # Clear result to prevent accidental unlock
        self.grab_release()
        self.destroy()
        self.controller.forgot_password()

class ServerDialog(BaseDialog):
    """Dialog for adding or editing a server."""
    def __init__(self, parent, title="Server Details", initial_data=None):
        super().__init__(parent, title=title)
        
        initial_data = initial_data or {}
        self.error_label = ctk.CTkLabel(self, text="", text_color="red")
        self.error_label.grid(row=5, column=0, columnspan=2, padx=10, pady=(0, 5))

        # --- Name ---
        ctk.CTkLabel(self, text="Server Name:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.name_entry = ctk.CTkEntry(self, width=250)
        self.name_entry.grid(row=0, column=1, padx=10, pady=5)
        self.name_entry.insert(0, initial_data.get("name", ""))
        
        # --- IP Address ---
        ctk.CTkLabel(self, text="IP Address:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.ip_entry = ctk.CTkEntry(self, width=250)
        self.ip_entry.grid(row=1, column=1, padx=10, pady=5)
        self.ip_entry.insert(0, initial_data.get("ip_address", ""))

        # --- Sudo Username ---
        ctk.CTkLabel(self, text="Sudo Username:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.user_entry = ctk.CTkEntry(self, width=250)
        self.user_entry.grid(row=2, column=1, padx=10, pady=5)
        self.user_entry.insert(0, initial_data.get("user", "root"))

        # --- SSH Password (for bootstrap) ---
        ctk.CTkLabel(self, text="SSH Password:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.pass_entry = ctk.CTkEntry(self, show="*", width=250)
        self.pass_entry.grid(row=3, column=1, padx=10, pady=5)
        
        # --- Buttons ---
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=20)
        
        ok_button = ctk.CTkButton(button_frame, text="Save", command=self._on_ok)
        ok_button.pack(side="left", padx=10)
        
        cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel)
        cancel_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        name = self.name_entry.get()
        ip_address = self.ip_entry.get()
        user = self.user_entry.get()
        password = self.pass_entry.get()

        if not name or not ip_address or not user or not password:
            ErrorDialog(self, message="All fields are required.")
            return

        self.result = {
            "name": name,
            "ip_address": ip_address,
            "user": user,
            "password": password
        }
        super()._on_ok()
        
class TunnelDialog(BaseDialog):
    """Dialog for adding or editing a tunnel."""
    def __init__(self, parent, controller, title="Tunnel Details", initial_data=None):
        super().__init__(parent, title=title)
        self.controller = controller
        initial_data = initial_data or {}

        self.grid_columnconfigure(1, weight=1)
        self.error_label = ctk.CTkLabel(self, text="", text_color="red")
        self.error_label.grid(row=6, column=0, columnspan=2, padx=10, pady=(0, 5))

        # Server Selection
        ctk.CTkLabel(self, text="Server:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.server_map = {s['name']: s['id'] for s in self.controller.get_servers()}
        self.server_menu = ctk.CTkOptionMenu(self, values=list(self.server_map.keys()))
        self.server_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        if initial_data.get("server_id"):
             for name, sid in self.server_map.items():
                if sid == initial_data["server_id"]:
                    self.server_menu.set(name)
        elif self.server_map:
            self.server_menu.set(list(self.server_map.keys())[0])

        # Hostname
        ctk.CTkLabel(self, text="Hostname:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.hostname_entry = ctk.CTkEntry(self, width=250)
        self.hostname_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.hostname_entry.insert(0, initial_data.get("hostname", ""))

        # Remote Port
        ctk.CTkLabel(self, text="Remote Port:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.remote_port_entry = ctk.CTkEntry(self, width=250)
        self.remote_port_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        self.remote_port_entry.insert(0, str(initial_data.get("remote_port", "")))

        # Local Destination
        ctk.CTkLabel(self, text="Local Destination:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.local_dest_entry = ctk.CTkEntry(self, width=250)
        self.local_dest_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")
        self.local_dest_entry.insert(0, initial_data.get("local_destination", "localhost:"))

        # Enabled Checkbox
        self.enabled_var = ctk.BooleanVar(value=initial_data.get("enabled", True))
        self.enabled_check = ctk.CTkCheckBox(self, text="Enabled", variable=self.enabled_var)
        self.enabled_check.grid(row=4, column=1, padx=10, pady=10, sticky="w")

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=5, column=0, columnspan=2, padx=20, pady=20)
        
        ok_button = ctk.CTkButton(button_frame, text="Save", command=self._on_ok)
        ok_button.pack(side="left", padx=10)
        
        cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel)
        cancel_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        try:
            if not self.server_map:
                ErrorDialog(self, message="Please add a server first.")
                return

            server_id = self.server_map[self.server_menu.get()]
            hostname = self.hostname_entry.get()
            remote_port = int(self.remote_port_entry.get())
            local_destination = self.local_dest_entry.get()
            
            if not hostname or not local_destination:
                ErrorDialog(self, message="Hostname and Local Destination are required.")
                return

            self.result = {
                "server_id": server_id,
                "hostname": hostname,
                "remote_port": remote_port,
                "local_destination": local_destination,
                "enabled": self.enabled_var.get(),
            }
            super()._on_ok()
        except (ValueError, KeyError) as e:
            logging.error(f"Tunnel Dialog Validation Error: {e}")
            ErrorDialog(self, message=f"Invalid input: {e}")


class InviteDialog(BaseDialog):
    """Dialog to display the sync invitation string and QR code."""
    def __init__(self, parent, invite_string: str):
        super().__init__(parent, title="Add a New Device")
        
        ctk.CTkLabel(self, text="On your new device, scan this QR code or copy the string:").pack(padx=20, pady=10)
        
        # Generate and display the QR code image
        qr_img = qrcode.make(invite_string)
        qr_img_pil = qr_img.resize((250, 250))
        self.qr_photo = ImageTk.PhotoImage(qr_img_pil)

        qr_label = ctk.CTkLabel(self, image=self.qr_photo, text="")
        qr_label.pack(padx=20, pady=10)
        
        invite_entry = ctk.CTkEntry(self, width=400)
        invite_entry.insert(0, invite_string)
        invite_entry.pack(padx=20, pady=10)
        
        close_button = ctk.CTkButton(self, text="Close", command=self._on_cancel)
        close_button.pack(pady=20)

class ConfirmationDialog(BaseDialog):
    """A generic yes/no confirmation dialog."""
    def __init__(self, parent, title="Confirm", message="Are you sure?"):
        super().__init__(parent, title=title)

        ctk.CTkLabel(self, text=message, wraplength=300).pack(padx=20, pady=20)
        
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=20)

        yes_button = ctk.CTkButton(button_frame, text="Yes", command=self._on_ok)
        yes_button.pack(side="left", padx=10)
        
        no_button = ctk.CTkButton(button_frame, text="No", command=self._on_cancel)
        no_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        self.result = True
        super()._on_ok()

class RecoveryKeyDialog(BaseDialog):
    """
    A dialog to display or input the recovery key.
    
    Args:
        parent: The parent window.
        recovery_key: The key to display (if in display mode).
        input_mode: If True, the dialog is for input, not display.
    """
    def __init__(self, parent, recovery_key: str = None, input_mode: bool = False):
        title = "Enter Recovery Key" if input_mode else "Save Your Recovery Key!"
        super().__init__(parent, title=title)
        
        if input_mode:
            message = "Enter your recovery key to reset your password:"
            ctk.CTkLabel(self, text=message, wraplength=350).pack(padx=20, pady=10)
            
            self.key_entry = ctk.CTkEntry(self, width=350, font=("Courier", 14))
            self.key_entry.pack(padx=20, pady=10)
            self.key_entry.focus_set()
            self.key_entry.bind("<Return>", self._on_ok)

            button_frame = ctk.CTkFrame(self, fg_color="transparent")
            button_frame.pack(padx=20, pady=20)
            ok_button = ctk.CTkButton(button_frame, text="OK", command=self._on_ok)
            ok_button.pack(side="left", padx=10)
            cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel)
            cancel_button.pack(side="left", padx=10)

        else: # Display Mode
            message = "This is your recovery key. It is the only way to regain access if you forget your master password. Please save it in a secure place."
            ctk.CTkLabel(self, text=message, wraplength=350).pack(padx=20, pady=10)
            
            key_entry = ctk.CTkEntry(self, width=350, font=("Courier", 14))
            key_entry.insert(0, recovery_key)
            key_entry.configure(state="readonly")
            key_entry.pack(padx=20, pady=10)

            self.confirm_check_var = ctk.StringVar(value="off")
            confirm_check = ctk.CTkCheckBox(self, text="I have saved this key in a secure place.",
                                            variable=self.confirm_check_var, onvalue="on", offvalue="off")
            confirm_check.pack(padx=20, pady=10)
            
            self.ok_button = ctk.CTkButton(self, text="Continue", command=self._on_ok, state="disabled")
            self.ok_button.pack(pady=20)

            # Link the checkbox to the button's state
            self.confirm_check_var.trace_add("write", self._check_state)

    def _check_state(self, *args):
        if self.confirm_check_var.get() == "on":
            self.ok_button.configure(state="normal")
        else:
            self.ok_button.configure(state="disabled")

    def _on_ok(self, event=None):
        if hasattr(self, 'key_entry'):
            self.result = self.key_entry.get()
        else:
            self.result = True
        super()._on_ok()

class ErrorDialog(BaseDialog):
    """A simple dialog to display an error message to the user."""
    def __init__(self, parent, message: str):
        super().__init__(parent, title="Error")

        ctk.CTkLabel(self, text=message, wraplength=300).pack(padx=20, pady=20)
        
        ok_button = ctk.CTkButton(self, text="OK", command=self._on_ok)
        ok_button.pack(pady=10)
