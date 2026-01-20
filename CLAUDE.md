# CLAUDE.md - AI Assistant Guide for YouTube Uploader

## Project Overview

This is a Python-based YouTube video uploader tool that automates bulk video uploads to YouTube using the YouTube Data API v3. The project is licensed under MIT License (Copyright 2021 Wang CHEN).

**Primary Purpose**: Upload single videos or entire folders of videos to a YouTube channel while respecting Google API quota limits and avoiding duplicate uploads.

**Key Features**:
- Batch upload videos from a folder
- Track uploaded videos to prevent duplicates
- OAuth2 authentication with Google
- Automatic quota management (max ~6 uploads per run based on Google API limits)
- Videos set to private by default with configurable metadata

## Codebase Structure

```
youtuber_uploader/
├── main.py              # Main uploader class and entry point
├── GoogleService.py     # OAuth2 service creation and authentication
├── README.md           # Setup and usage instructions
├── LICENSE             # MIT License
├── .gitignore          # Git ignore patterns
└── secret/             # OAuth2 credentials (git-ignored)
    └── secret.json     # Client secret file from Google Cloud Console
```

### Core Files

#### `main.py` (Primary file - 115 lines)
Contains the `YoutubeUploader` class with the following key components:

**Class Constants**:
- `CLIENT_SECRET_FILE`: Path to OAuth2 credentials (`./secret/secret.json`)
- `API_NAME`, `API_VERSION`, `SCOPES`: YouTube API configuration
- `MAX_UPLOAD_NUM`: Upload limit per run (6 videos, based on 10,000 quota / 1,600 per upload)
- `UPLOADED_FILES_TXT`: Tracking file for uploaded videos (`./uploaded_files.txt`)
- `TAGS`: Video tags (empty list by default)

**Key Methods**:
- `__init__()`: Initializes OAuth2 service (line 21-24)
- `get_request_body(title)`: Prepares upload metadata (line 26-46)
- `upload_video(video_file_path, request_body)`: Uploads single video (line 48-61)
- `add_info_to_txt(info)`: Records uploaded video paths (line 63-71)
- `get_file_list_from_txt()`: Retrieves list of already uploaded videos (line 73-85)
- `upload_videos_from_folder(video_folder_path, video_ext)`: Batch upload handler (line 87-106)

**Entry Point** (line 108-114):
- Sets socket timeout to 30000 seconds
- Default video folder: `D:\download` (Windows path - needs modification for other systems)
- Default video extension: `.mp4`

#### `GoogleService.py` (Authentication module - 50 lines)
Contains the `Create_Service()` function for OAuth2 authentication:

**Function**: `Create_Service(client_secret_file, api_name, api_version, *scopes)`
- Creates/loads OAuth2 token pickle file: `token_{API_SERVICE_NAME}_{API_VERSION}.pickle`
- Handles token refresh automatically
- Opens browser for initial OAuth2 flow
- Returns authenticated Google API service object

**Authentication Flow**:
1. Check for existing token pickle file
2. If token exists and is valid, use it
3. If token expired, refresh it
4. If no valid token, run OAuth2 flow in browser
5. Save token to pickle file for reuse

## Development Workflows

### Setting Up for Development

1. **Create Google Cloud Project**:
   - Follow: https://www.youtube.com/watch?v=6bzzpda63H0
   - Enable YouTube Data API v3
   - Create OAuth2 credentials (Desktop app type)
   - Download `client_secret.json` and save to `./secret/secret.json`

2. **Set Up Python Environment**:
   ```bash
   conda create --name youtube python=3.9
   conda activate youtube
   pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
   ```

3. **Verify YouTube Account**: Check https://www.youtube.com/verify

4. **Test OAuth2 Setup**:
   ```bash
   python GoogleService.py
   ```

5. **Configure Redirect URIs** (if needed):
   - Go to https://console.cloud.google.com/apis/credentials/
   - Add `http://localhost:8080/` to Authorized redirect URIs

### Making Code Changes

**For Upload Configuration Changes**:
- Modify class constants in `YoutubeUploader` (main.py:13-19)
- Common changes:
  - `TAGS`: Add default video tags
  - `privacyStatus`: Change from 'private' to 'public' or 'unlisted' (line 42)
  - `selfDeclaredMadeForKids`: Adjust for content type (line 43)

**For Adding New Features**:
- Keep changes in `main.py` (YoutubeUploader class)
- Avoid modifying `GoogleService.py` unless changing authentication
- Add new methods following existing naming conventions (snake_case)
- Update type hints for all parameters and return values

**For API Changes**:
- Reference: https://developers.google.com/youtube/v3/docs/videos/insert
- Modify `get_request_body()` method for different metadata
- Add new API methods using `self.service` object

## Key Conventions

### Code Style

1. **Type Hints**: All functions use type hints
   ```python
   def method(self, param: Type) -> ReturnType:
   ```

2. **Docstrings**: Google-style docstrings for all methods
   ```python
   """Brief description

   Args:
       param (type): [description]

   Returns:
       type: [description]
   """
   ```

3. **Path Handling**: Use `pathlib.Path` for all file operations
   - Example: `Path(r"./uploaded_files.txt")`
   - Use raw strings (r"") for Windows compatibility

4. **Constants**: UPPER_SNAKE_CASE for class-level constants

5. **Methods**: snake_case for method names

### Important Patterns

1. **File Tracking**: Videos are tracked in `uploaded_files.txt` to prevent re-uploads
   - Format: One file path per line
   - Read before upload, write after successful upload

2. **Error Handling**: Minimal error handling currently
   - OAuth errors surface to user for manual resolution
   - API errors print to console

3. **Quota Management**: Hardcoded limit of 6 uploads per execution
   - Based on Google's 10,000 quota units/day limit
   - Each upload costs ~1,600 quota units
   - Formula: `int(10_000 / 1_600)` = 6 (line 17)

4. **Video Metadata**: All videos use filename (without extension) as title and description

## Critical Considerations for AI Assistants

### Security

1. **Never commit or expose**:
   - `./secret/secret.json` (OAuth2 client secret)
   - `*.pickle` files (OAuth2 tokens)
   - `uploaded_files.txt` may contain sensitive paths

2. **Git-ignored files** (see .gitignore:29-31):
   - `secret/` directory
   - `*.pickle` files
   - `*.txt` files

### API Limitations

1. **Google API Quota**:
   - Daily limit: 10,000 quota units
   - Per video upload: ~1,600 units
   - Practical limit: 6 videos per day per project
   - Exceeding quota returns 403 errors

2. **API Scope**: Only has upload permission
   - SCOPES: `['https://www.googleapis.com/auth/youtube.upload']`
   - Cannot read, modify, or delete existing videos
   - Cannot access analytics or other YouTube features

### Common Issues and Solutions

1. **Error 400: redirect_uri_mismatch**:
   - Add `http://localhost:8080/` to OAuth2 Authorized redirect URIs
   - Location: Google Cloud Console > APIs & Credentials

2. **Error 403: API not enabled**:
   - Enable YouTube Data API v3 in Google Cloud Console
   - Follow error message URL to enable

3. **Socket timeout issues**:
   - Timeout set to 30000 seconds (line 111)
   - Large video files may still timeout on slow connections

4. **Path compatibility**:
   - Default path is Windows-style: `D:\download`
   - Must be updated for Linux/Mac: `/home/user/videos` or similar

### Testing Checklist

Before running modifications:
1. Verify `./secret/secret.json` exists and is valid
2. Check OAuth2 token pickle file exists or can be created
3. Verify video folder path is correct for the OS
4. Confirm video files have correct extension (.mp4 by default)
5. Check YouTube channel is verified for uploads
6. Ensure quota is available (check Google Cloud Console)

### Best Practices for Code Modifications

1. **Read before edit**: Always read both Python files before making changes
2. **Preserve type hints**: Maintain type annotations on all modifications
3. **Keep docstrings updated**: Update docstrings when changing method signatures
4. **Test authentication separately**: Run `GoogleService.py` standalone after auth changes
5. **Respect quota limits**: Don't increase `MAX_UPLOAD_NUM` beyond 6 without user confirmation
6. **Handle paths carefully**: Use `pathlib.Path` and consider cross-platform compatibility
7. **Preserve tracking mechanism**: Maintain `uploaded_files.txt` functionality to prevent duplicates
8. **Don't over-engineer**: This is a simple utility tool, keep changes minimal and focused

### File Organization Preferences

1. **Single file for logic**: Keep all upload logic in `main.py`
2. **Separate authentication**: Keep OAuth2 in `GoogleService.py`
3. **No additional modules**: Avoid creating new files unless absolutely necessary
4. **Configuration in class constants**: Don't create separate config files

### When Suggesting Changes

1. **Always mention quota implications** when changing upload behavior
2. **Warn about OAuth2 scope changes** if modifying SCOPES constant
3. **Consider cross-platform paths** when changing file paths
4. **Preserve backwards compatibility** with existing `uploaded_files.txt`
5. **Document privacy implications** when changing `privacyStatus`

## Quick Reference

### Running the Uploader
```python
from pathlib import Path
from main import YoutubeUploader

# Modify video_folder path as needed
video_folder = Path(r'/path/to/videos')
yt = YoutubeUploader()
yt.upload_videos_from_folder(video_folder, video_ext=".mp4")
```

### Supported Video Extensions
Default: `.mp4`
Compatible: `.mov`, `.avi`, `.flv`, `.wmv`, `.3gp`, etc.
(Change `video_ext` parameter)

### Video Upload Settings
- **Privacy**: Private (configurable in `get_request_body()`)
- **Notify Subscribers**: False
- **Made for Kids**: False (must be set correctly per content)
- **Title**: Video filename without extension
- **Description**: Same as title
- **Tags**: Empty (configurable via `TAGS` class constant)

## Common Modification Scenarios

### Change Video Privacy to Public
Edit `main.py:42`:
```python
'privacyStatus': 'public',  # Changed from 'private'
```

### Add Default Tags
Edit `main.py:19`:
```python
TAGS = ['tag1', 'tag2', 'tag3']
```

### Change Default Video Folder
Edit `main.py:112`:
```python
video_folder = Path(r'/home/user/my-videos')  # Linux/Mac
# or
video_folder = Path(r'C:\Users\Username\Videos')  # Windows
```

### Support Different Video Format
Edit `main.py:114`:
```python
yt.upload_videos_from_folder(video_folder, video_ext=".mov")
```

### Increase Upload Description Quality
Edit `main.py:38`:
```python
'description': f"Full video: {title}\n\nUploaded automatically",
```

---

**Last Updated**: 2026-01-20
**Repository**: youtuber_uploader
**Python Version**: 3.9+
**Primary Dependencies**: google-api-python-client, google-auth-httplib2, google-auth-oauthlib
