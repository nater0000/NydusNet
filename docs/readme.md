# NydusNet 🛡️

NydusNet is a secure and decentralized network management application built with Python and `customtkinter`. It provides a user-friendly graphical interface for managing SSH tunnels and synchronizing configuration files across multiple devices. The application prioritizes security by using a master password, a recovery key system, and an encrypted, version-controlled configuration.


## Features ✨

  * **Secure Tunnel Management**: Easily create, start, and stop SSH tunnels to your servers.
  * **Decentralized Configuration Sync**: Uses an embedded Syncthing instance to synchronize your encrypted configuration data across all your devices in real-time.
  * **Encrypted & Versioned History**: All configuration changes are encrypted with your master password and stored using a delta-based versioning system, allowing you to roll back to previous states.
  * **Automated Server Provisioning**: Integrates with an embedded Ansible engine to automatically set up new servers, handling tasks like user creation, SSH key deployment, and Syncthing installation.
  * **Conflict Resolution**: A built-in leader election and merge process handles configuration conflicts that may arise from simultaneous changes on different devices.


## User Installation 🚀

To run NydusNet, simply download and run the installer. All dependencies are included!

1.  **Download the Installer**:

      * Download the latest `NydusNet_Installer.exe` from the [Releases page](https://github.com/nater0000/nydusnet/releases) 📦.

2.  **Run the Installer**:

      * Double-click the downloaded `.exe` file and follow the on-screen instructions. The installer will set up NydusNet and its dependencies for you.

3.  **First-Time Setup**:

      * On the first launch, you'll be prompted to **create a master password**. Choose a strong, memorable password! This encrypts all your data 🔒.
      * The app will then generate a **one-time recovery key**. This key is the *only* way to restore access if you forget your master password. **Save it somewhere safe!** 🔑
      * Once your password is set, the app will launch, and you're ready to start managing your network!


## Development Environment Setup 🧑‍💻

Want to contribute or run from source? It's easier than ever before!

### Prerequisites

  * **Python 3.8+**: Ensure you have a compatible Python version installed.
  * **Git**: For cloning the repository.
  * **Inno Setup Compiler**: Required to create the final Windows installer package.

### Project Setup

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/nater0000/nydusnet.git
    cd nydusnet
    ```
2.  **Install Dependencies**:
      * The project uses `pyproject.toml` for dependency management.
    <!-- end list -->
    ```bash
    pip install .
    ```
3.  **Build the Application**:
      * Run the build script. This will automatically download the correct Syncthing executable, bundle all dependencies, and create the final installer file in the `Output` directory.
    <!-- end list -->
    ```bash
    python scripts/build.py
    ```


## Contributing 🤝

We welcome all contributions, ideas, and bug reports! Please check out our `CONTRIBUTING.md` file for more information on how to get started.