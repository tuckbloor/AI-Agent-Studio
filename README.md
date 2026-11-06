# AI Agent Studio v2.3.4

**Build, configure and run your own AI agents on a self-hosted AI App Server.** AI Agent Studio provides a visual interface for describing an agent, reviewing its workflow, selecting tools and monitoring what happens when it runs.

**Windows 10/11 · Python 3.11+ · Self-hosted · MIT licence**

> **Important:** AI Agent Studio **requires the AI App Server framework**. You do **not** have to install it manually beforehand: the Studio installer can use a compatible existing AI App Server **or install a separate AI App Server first**. Each Studio installation then gets its **own** framework copy, configuration, users, database and port. Studio does not modify the existing server.
>
> **Status:** Development release, intended for trusted local use. Do not expose it directly to the public internet without security and deployment review.

![AI Agent Studio builder](images/01-ai-builder.jpg)

## Features

- Create agents from plain-language instructions and review/edit the proposed steps.
- Select built-in tools and configure optional MCP tools, templates and read-only SQL Server tools.
- Choose locally installed **Ollama** models for AI-assisted workflows.
- Monitor execution, inspect tool results, and save, export or import compatible workflows.
- Manage Studio through its **own** AI App Server admin area, with separate accounts, storage and settings.

## Before installing

You need:

1. **Windows 10 or 11** and **Python 3.11 or later** (`py -3 --version` in PowerShell should work).
2. Internet access during the first installation to download Python dependencies.
3. The complete AI Agent Studio source ZIP, containing `INSTALL.bat`, `START.bat`, `app/`, `framework/` and `tools/`.
4. **AI App Server v1.0.4 or v1.0.5** as the framework. The v1.0.5 source is **included in this project**, so the installer can install it if it is missing.
5. **Optional:** [Ollama](https://ollama.com/) and a downloaded model to use AI-powered features. The interface can run without Ollama, but model-powered agents need a running model provider.

Download the repository with **Code → Download ZIP**, or use the [releases page](https://github.com/tuckbloor/AI-Agent-Studio/releases). Extract it to **any writable directory**; the source folder can be on C:, D:, E:, your Desktop or elsewhere. The chosen *installation* locations can be different from the extracted source folder. No fixed drive letter is required.

## Install on Windows — illustrated guide

Double-click **`INSTALL.bat`** in the extracted source folder. A short-lived console may appear and close; the **AI Agent Studio installer window remains open** while you choose folders, install and review messages.

### The installation window

![AI Agent Studio v2.3.4 installer showing server selection, installation paths and a successful installation](images/Screenshot%202026-11-06%20230159.png)

*Screenshot: v2.3.4 installer after a successful installation. The log at the bottom confirms that Studio was registered for Windows sign-in startup and started on port 8502. Your paths and port may be different.*

The numbered sections in the picture correspond to these steps:

**1. AI App Server framework**

- **Use an existing AI App Server (read-only)** — choose this if AI App Server is already installed. Click **Browse...** to locate its installation directory. The installer checks compatibility and **uses its framework code as a source**; it does **not** replace or alter the existing installation, its database or its admin users.
- **Install a new AI App Server first** — choose this if you do not have a compatible server. Select a **new, empty and writable** folder for the server. The installer asks before installing the bundled AI App Server v1.0.5, then installs Studio separately.
- **AI App Server location** — the top path in the screenshot is an example of an existing server: `C:\Users\User\AppData\Local\Programs\AI-App-Server`. On another computer the location may differ. **Do not choose the Studio folder here.**

**2. AI Agent Studio destination**

- Choose where **Studio itself** will be installed, such as `%LOCALAPPDATA%\Programs\AI-Agent-Studio`, `C:\AI-Agent-Studio` or `D:\AI-Agent-Studio`.
- This must be a **different folder** from AI App Server. A new destination should be empty.
- If the folder already contains a **recognised AI Agent Studio installation**, you are asked whether to overwrite the *application files*. **Yes** creates a backup and updates the managed code while keeping the database, agents, users and settings. **No** makes no changes. An unrelated non-empty folder is never overwritten.

**3. Install / Update**

- Click **Install / Update**. The installer sets up Studio's isolated Python environment, copies its own framework, prepares its application and verifies its routes.
- Read the progress box at the bottom of the window. **Leave the window open until it reports success or a readable error.** You can scroll back through the messages; the installer also writes a log under `%LOCALAPPDATA%\AI-Agent-Studio\logs`.
- A successful run displays **“Installation completed successfully. Studio is ready.”** The screenshot shows an example with **Administration: `http://127.0.0.1:8502/admin`** and a backup of the previous application.
- **Open installed folder** opens the chosen Studio installation directory. **Close** closes the completed installer.

### First run and sign-in

On success, the installer attempts to start Studio and open it in your browser. **Use the port shown in your own install log** — it may differ from the example because AI App Server and Studio have **independent ports**.

| Destination | Address (replace `PORT`) |
|---|---|
| Studio homepage | `http://127.0.0.1:PORT/` |
| Studio admin sign-in | `http://127.0.0.1:PORT/admin` |
| Agent builder | `http://127.0.0.1:PORT/admin/studio` |
| Health check | `http://127.0.0.1:PORT/health` |

For the successful installation in the screenshot, use `http://127.0.0.1:8502/admin` and `http://127.0.0.1:8502/admin/studio`. The separate AI App Server may be on port **8501**; that is **not** necessarily Studio's address.

On your first admin sign-in, follow the application's initial administrator/password-change prompts. Use a strong unique password. If you have updated an existing Studio installation, its existing user accounts and settings are retained.

## Start or stop Studio later

Open the **installed Studio directory**, rather than the original downloaded ZIP, and double-click:

```text
START.bat
```

You can also run these commands in PowerShell **from the installed Studio directory**:

```powershell
.\START.bat --status
.\START.bat --stop
.\START.bat --disable-autostart
```

- `--status` checks the Studio instance.
- `--stop` stops Studio's own server, not the separate AI App Server.
- `--disable-autostart` removes Studio's Windows sign-in startup entry.

The source folder's `START.bat` can locate the remembered Studio installation or let you browse to it. If the install never completed, use `INSTALL.bat` from the extracted source rather than starting the source folder as an application.

### Create a desktop shortcut

1. Open the **installed Studio folder** (the second location selected in the installer).
2. Right-click **`START.bat`**. On Windows 11, first choose **Show more options**, if needed.
3. Choose **Send to → Desktop (create shortcut)**.
4. Rename the shortcut **AI Agent Studio**.
5. Double-click that shortcut whenever you want to start Studio.

You can also create a browser shortcut to your own Studio URL (`http://127.0.0.1:PORT/admin/studio`), but this only opens the page: it **does not start** a stopped server.

### Automatic startup or a Windows Service?

A normal successful installation configures **per-user Windows sign-in startup** for Studio. To view that shortcut, press **Win + R**, enter `shell:startup`, then press Enter. This starts Studio **after you sign in** to Windows.

This **is not a Windows Service**. It does not guarantee Studio runs before anyone signs in, and the Studio installer does not register a Windows Service. Running as a true service needs a separately configured, tested service installation and appropriate Windows permissions. Do not confuse sign-in startup with a production service.

## Build your first agent

1. Install and start [Ollama](https://ollama.com/) if you want to use a local AI model. For example, open PowerShell and run `ollama pull llama3.2`, then check that Ollama is running.
2. Open **Studio's** `/admin/studio` address and sign in as your Studio administrator.
3. Select an available model in the Studio interface.
4. Describe the task you want the agent to perform. For example: *“Research a topic, compare reliable sources and summarise the findings with links.”*
5. Review the proposed steps and tools. Allow only the tools and permissions needed for the task.
6. Run the agent, watch the live execution feedback, inspect the results and save or export the workflow when satisfied.

MCP tools must be explicitly configured. SQL Server tools are read-only where provided and configured. Do not put passwords, tokens or sensitive information in exported workflows.

## Using an existing server versus installing a new one

| Situation | Choice in the installer | What happens |
|---|---|---|
| AI App Server is already installed | **Use an existing AI App Server (read-only)** | Its compatible framework files are reused **as a source**, but the existing running installation is unchanged. |
| AI App Server is not installed | **Install a new AI App Server first** | The bundled v1.0.5 server is installed to a separate chosen folder, then Studio is installed. |
| Studio already exists | Select the recognised existing Studio directory | You are asked **Yes/No** before a backed-up application-code update. |
| You want Studio on another drive | Browse to the desired Studio directory | The installer uses the selected path; no E: drive is required. |

**Isolation matters:** AI Agent Studio runs as its **own** AI App Server instance. Its accounts, database, maintenance settings and ports are separate from any existing AI App Server or other AI projects. The installer does **not** install Studio inside another application's admin dashboard.

## Update safely

1. Download and extract the newer **complete** Studio source to a folder outside your live installation.
2. Keep your current installed Studio and its data intact. Do **not** delete them.
3. Double-click the new source's `INSTALL.bat` and select the same existing Studio destination.
4. When the installer recognises Studio and asks whether to overwrite its application files, choose **Yes** to create a backup and update, or **No** to cancel.
5. Wait for the verification result, then check the admin login, agents and saved workflows.

The installer aims to preserve `data/`, `config/`, user-owned app code and other user content while refreshing managed application files. Back up your important data separately before any upgrade; a backed-up code refresh is **not** a guarantee that all future major versions can migrate old databases automatically. An existing separate AI App Server is **not upgraded** during a Studio update.

If a prior installation stopped during setup, an advanced recovery command is available from the extracted **v2.3.4 source folder**:

```powershell
.\INSTALL.bat --resume "C:\Path\To\Installed\AI-Agent-Studio"
```

Replace that example with your actual installed Studio path. Recovery checks the recognised Studio installation and completes missing setup without deliberately replacing user data.

## Troubleshooting

| Symptom | What to do |
|---|---|
| Python is not found | Install Python 3.11+ and check `py -3 --version` in a new PowerShell window. |
| Installer command window disappears | That brief console is expected to close when the persistent graphical installer opens. If the **GUI** does not appear, run `py -3 tools\studio_gui.py` from the source directory to see the error. |
| No existing AI App Server is detected | Browse to the correct compatible installation directory, or choose **Install a new AI App Server first**. |
| Destination contains an existing Studio | Choose **Yes** to perform the backed-up application-code update, or **No** to leave it unchanged. |
| Destination contains unrelated files | Choose a different, empty folder; the installer intentionally will not overwrite unrelated files. |
| You can't find the Studio URL | Read the **Administration:** line in the installer log or run `START.bat --status` in the installed folder. Do not assume port 8501. |
| Agent model dropdown is empty | Start Ollama, download a model and make sure Studio can reach your local provider. |
| Studio won't start | Review the installation log in `%LOCALAPPDATA%\AI-Agent-Studio\logs` and the installed application's `data\logs` directory. |
| Studio doesn't start at Windows sign-in | Check `shell:startup`. Sign-in startup and Windows Services are different features. |

## Project screenshots

| Agent builder | Workflow review |
|---|---|
| ![Agent builder](images/01-ai-builder.jpg) | ![Workflow review](images/02-ai-workflow-review.jpg) |

| Visual workflow editor | Tool selection |
|---|---|
| ![Visual workflow editor](images/03-visual-workflow-editor.jpg) | ![Tool selection](images/04-multiple-tools.jpg) |

![Live execution monitor](images/05-live-execution-monitor.jpg)

## Source, development and tests

The Windows distribution has only **two BAT files**: `INSTALL.bat` and `START.bat`. The installer code is under `tools/`, the Studio application is under `app/studio_integration/`, and the packaged AI App Server framework is under `framework/`.

For development testing from the extracted source directory:

```powershell
py -3 -m pip install -e ".\framework\engine[dev]"
py -3 -m pytest -q
```

Local installation requires a suitable Windows environment. Tests in CI are useful checks but do not replace testing installation, startup and updates on a real Windows machine.

## Version, security and licence

- **AI Agent Studio:** v2.3.4
- **Bundled AI App Server framework:** v1.0.5 (also recognises compatible existing v1.0.4 installations)
- **Licence:** MIT — see [LICENSE](LICENSE)
- **Repository:** [github.com/tuckbloor/AI-Agent-Studio](https://github.com/tuckbloor/AI-Agent-Studio)

Self-hosting does not automatically make an application safe to expose publicly. Use a trusted local environment, secure administrator credentials, and review your dependencies and deployment configuration before opening network access.
