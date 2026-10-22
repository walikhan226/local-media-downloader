# Local Media

A small local web app for downloading videos from public links on YouTube, Instagram, TikTok, and other sites supported by yt-dlp, or extracting MP3 audio. Extractor availability can change as platforms update their sites. Private or login-gated posts may not work. Use it only for content you own or have permission to download, and follow the source platform's terms. It does not bypass DRM, paywalls, or access controls.

## Windows setup

1. Install Python 3.10 or later, Node.js/npm, and [FFmpeg](https://ffmpeg.org/download.html). FFmpeg must be available on PATH.
2. Double-click `start.bat`. It installs yt-dlp and its YouTube support scripts, installs Deno in the app folder through the npm distribution if needed, and starts the local app.
3. Use the browser page opened at [http://127.0.0.1:8765](http://127.0.0.1:8765). Downloads go in the `downloads` folder.

You can also run `python -m pip install -r requirements.txt` and `python server.py` from PowerShell after installing the dependencies. The server binds to your own computer only by default. Press Ctrl+C in the console to stop it.

## Supported sites

The app delegates site extraction to yt-dlp. YouTube, Instagram, and TikTok extractors are included in the upstream project, which maintains a current [supported sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). This is not a guarantee that every link will work: public posts are the best fit, while private, login-gated, region-restricted, or removed posts can fail as platforms change.
