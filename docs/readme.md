# **NydusNet 🛡️✨**

NydusNet is a secure, multi-device reverse SSH tunnel manager for Windows, built with Python and customtkinter. It provides a user-friendly graphical interface to securely expose your local services to the internet and synchronizes your configuration automatically across all your devices.

## **Core Features 🚀**

* **Effortless Tunnel Management**: Create, start, stop, edit, and delete reverse SSH tunnels with a clean, intuitive UI **featuring a collapsible sidebar**. ↔️
* **Multi-Device Sync**: Uses a bundled **Syncthing** instance to automatically and securely sync your encrypted configuration data across all your linked devices in real-time. 💻🔄💻
* **Zero-Config First Start**: On first launch, NydusNet automatically generates the necessary SSH keys. No manual `ssh-keygen` required! 🔑
* **Device-Specific Control**: Assign tunnels to be managed by specific devices. A tunnel assigned to your Desktop won't accidentally be started by your Laptop. **Tunnels can also be set to auto-start on specific devices.** 📍
* **Real-Time Status & Logs**: Tunnels now show their live status (**Connecting**, **Running**, **Error**). View detailed SSH logs directly within the app to diagnose connection issues instantly. 🚦📄
* **Rock-Solid Security**:
    * All configuration is encrypted at rest with a **master password** using strong PBKDF2 key derivation and AES-256 encryption. 🔒
    * A **recovery key** system ensures you can regain access if you forget your master password.
* **System Tray & Focus**: **Stays on top during setup (password/loading) for convenience,** then runs quietly in the background. Manage the app from a convenient system tray icon. 🖱️
* **Developer Debug Tools**: A built-in debug view allows you to inspect the raw, reconstructed JSON for all configuration objects. 🐞

## **Getting Started: A Quick Guide 🧭**

Follow these steps to set up your first tunnel.

### **Prerequisite: Authorize Your Computer on Your Server**

For NydusNet to connect to your server without a password, you must first tell your server to trust your computer.

1.  **Find Your Public Key** 🗝️
    * Open NydusNet and go to ⚙️ Settings -> Security tab.
    * The path to your **Public Key** is listed there. Open this file (e.g., `id_rsa.pub`) with a text editor and copy its entire contents. It will look like `ssh-rsa AAAA....`
2.  **Log In to Your Server** 🖥️
    * Use a terminal or an SSH client like PuTTY to connect to your server with a user that has sudo or root privileges.
    * `ssh your_user@your_server_ip`
3.  Create a Tunnel User (Recommended) 🧑‍🚀
    It's best practice to use a separate, non-privileged user for your tunnels.
    ```bash
    # Create a new user, for example 'tunnel'
    sudo adduser tunnel

    # Switch to the new user
    sudo su - tunnel
    ```
4.  **Add Your Public Key** ✅
    * As the tunnel user, create the SSH directory and the `authorized_keys` file.
    ```bash
    # These commands will create the file and directory if they don't exist
    mkdir -p ~/.ssh
    nano ~/.ssh/authorized_keys
    ```
    * Paste your public key into this file. Save and exit (`Ctrl+X`, `Y`, `Enter`).
    * **Crucially, set the correct permissions:**
    ```bash
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys
    ```
    Your server is now ready!

### **Step 1: Add the Server to NydusNet**

1.  Go to ⚙️ Settings -> Servers tab.
2.  Click ➕ Add New Server.
3.  Fill in the details:
    * **Server Name**: A friendly name (e.g., "My Web Server").
    * **IP Address**: The public IP of your server.
    * **Sudo Username**: The admin user (e.g., `root`). This is needed for future automation features.
    * **Tunnel Username**: The non-privileged user you created (e.g., `tunnel`). **This is the user the tunnels will connect as.**
    * **Sudo Password**: The password for the admin user.
4.  Click **Save**.

### **Step 2: Create Your First Tunnel**

1.  Go back to the main **Dashboard**.
2.  Click ➕ Add New Tunnel.
3.  Fill in the tunnel details:
    * **Server**: Select the server you just added.
    * **Managed By**: Choose which of your devices is responsible for starting/stopping this tunnel.
    * **Hostname**: A friendly name for the local service (e.g., `plex`, `web-app`).
    * **Remote Port**: The public port on your server that will receive traffic (e.g., `80`, `443`, `8080`).
    * **Local Destination**: The address and port of the service running on your local computer (e.g., `localhost:3000`, `192.168.1.50:8123`). We recommend using `localhost:PORT`.
4.  Check **"Auto-start on this device?"** if you want it to connect when NydusNet launches.
5.  Click **Save**.

### **Step 3: Manage Your Tunnels**

Your new tunnel will now appear on the dashboard!

* **Status Light (●)**: Shows the current state:
    * ⚪ **Gray**: Stopped
    * 🟠 **Orange**: Connecting
    * 🟢 **Green**: Running
    * 🔴 **Red**: Error
* **▶️ Start / ⏹️ Stop**: Starts or stops the tunnel. This will be disabled if the tunnel is managed by another device.
* **✏️ Edit**: Modify the tunnel's configuration.
* **📄 Logs**: View the detailed, real-time SSH connection log. Invaluable for debugging!
* **🗑️ Delete**: Permanently remove the tunnel.

> **⚠️ Important Note on Stopping Tunnels:**
>
> * The **⏹️ Stop** button currently terminates the *local* `ssh.exe` process. This successfully stops traffic and allows you to restart the tunnel from the UI, but it **does not gracefully close the connection on your server**. The server-side port may remain open (orphaned) until the server's SSH service times it out.
> * To perform a **graceful shutdown** that properly closes the connection on both your client and the server, **close the entire NydusNet application** (either from the window 'X' button or the system tray 'Quit' option).
>
> A fix to make the Stop button perform a graceful shutdown is under investigation.

## **Roadmap 🗺️: The Road to Fabric!**

Our next major goal is to implement **automated server provisioning** using the **Fabric** library.

This feature was originally planned using Ansible, but that approach was abandoned due to insurmountable packaging issues on Windows. Fabric, being a pure-Python library, is a much more robust and cross-platform solution for our needs.

The Fabric integration will allow you to:

1.  **Provision a New Server with One Click** 🖱️💨: From the NydusNet UI, you'll be able to provide root credentials for a fresh VPS.
2.  **Automated Setup**: NydusNet will then automatically:
    * Connect to the server.
    * Create a secure, non-privileged tunnel user.
    * Upload your public SSH key to the tunnel user's `authorized_keys` file.
    * Configure the server's SSH service for optimal security and reliability.

This will complete the vision of a fully self-contained, easy-to-use tunneling solution!

## **User Installation 📦**

To run NydusNet, simply download and run the installer. All dependencies are included!

1.  **Download the Installer**:
    * Download the latest `NydusNet_Installer.exe` from the [Releases page](https://github.com/nater0000/nydusnet/releases).
2.  **Run the Installer**:
    * Double-click the downloaded .exe file and follow the on-screen instructions.
3.  **First-Time Setup**:
    * On the first launch, you'll be prompted to **create a master password**. Choose a strong, memorable password! This encrypts all your data 🔒.
    * The app will then generate a **one-time recovery key**. This key is the *only* way to restore access if you forget your master password. **Save it somewhere safe!** 🔑
    * Once your password is set, the app will launch, and you're ready to start managing your network!

## **Development Environment Setup 🧑‍💻**

Want to contribute or run from source? Here’s how to get set up.

### **Prerequisites**

* **Python 3.8+**
* **Git**

### **Project Setup**

1.  **Clone the Repository**:
    ```bash
    git clone [https://github.com/nater0000/nydusnet.git](https://github.com/nater0000/nydusnet.git)
    cd nydusnet
    ```
2.  **Install Dependencies**:
    * The project uses `pyproject.toml` for dependency management. Install in editable mode:
    ```bash
    pip install -e .
    ```
3.  **Run the Application**:
    * The main script will start an instance of the application connected and writing to the console that launches it.
    ```bash
    python src/main.py
    ```
    > or
    >
    > Double-click the icon after installation succeeds

4.  **Build the Standalone Executable**:
    * The build script will automatically download the correct Syncthing executable and use PyInstaller to create a single .exe file in the `dist` directory.
    ```bash
    python build.py
    ```
