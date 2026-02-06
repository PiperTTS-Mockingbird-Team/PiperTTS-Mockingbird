# Google Docs Add-on Installation 📄

This add-on allows you to read your Google Docs aloud using your local PiperTTS Mockingbird server.

## 🛠️ Setup Instructions

Google Docs Add-ons for local servers require a bit of manual setup since they run in the Google Cloud environment but need to "talk" to your local computer.

### 1. Open the Apps Script Editor
1. Open any Google Doc.
2. Go to **Extensions** > **Apps Script**.

### 2. Copy the Files
1. Copy the contents of [`Code.gs`](Code.gs) into the `Code.gs` file in the Apps Script editor.
2. Create a new HTML file in the editor (Click **+** > **HTML**) and name it `Sidebar`.
3. Copy the contents of [`Sidebar.html`](Sidebar.html) into that file.
4. Save the project (File > Save).

### 3. Configure Your Server Connection

The add-on can work in two ways:

**If your computer and Google Docs are on the same network:**
- Just use `http://localhost:5002` (or your computer's local IP like `http://192.168.1.10:5002`)

**If you need remote access:**
Since Google Docs runs in the cloud, you'll need to expose your local server using a tunnel:
- **Recommended:** Use [ngrok](https://ngrok.com/) or [Cloudflare Tunnel](https://www.cloudflare.com/products/tunnel/)
- Run: `ngrok http 5002`
- Copy the public URL (e.g., `https://abc123.ngrok.io`)
- Paste it into the **Server URL** field in the add-on sidebar

### 4. Run the Add-on
1. Back in your Google Doc, refresh the page.
2. You should see a new menu item: **Add-ons** > **Piper Speak** > **Open Piper Speak**.
3. A sidebar will appear on the right.
4. You may be asked to authorize the script on first run. Click **Allow**.

### 5. Start Reading
1. In the sidebar, verify the **Server URL** field shows your server address.Consider:
- Using ngrok's password protection feature
- Only running the tunnel when you need it
- Enabling an API key in your Mockingbird server settings (advanced users can modify the fetch headers in `Sidebar.html` to include authentication)
2. Check that the status indicator shows a green dot (server connected).
3. Click **▶ Read Document** to start reading your document aloud!

The add-on will:
- Read through your document sentence by sentence
- Highlight each sentence as it speaks
- Show playback controls (Pause/Stop)

## 🔒 Security Note
When using a public tunnel, anyone with the link could potentially use your TTS server. It is highly recommended to enable an **API Key** in your `src/config.json` and update the headers in `Code.gs` to match.
