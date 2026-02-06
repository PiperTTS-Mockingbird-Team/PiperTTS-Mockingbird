# Mockingbird Extension - Changelog

## [Current Version] - Feature Update

## Version 2.1.0 - OCR Support Update

### 🎉 New Features

#### Offline OCR (Optical Character Recognition)
- **Extract Text from Images**: Right-click any image and select "Extract text from image (OCR)"
- **Powered by Tesseract.js**: Fully offline, browser-based OCR processing
- **Multi-language Support**: Supports 11+ languages including:
  - English, Spanish, French, German, Italian, Portuguese
  - Russian, Arabic, Chinese Simplified, Japanese, Korean
- **Read Extracted Text**: Automatically read aloud extracted text or copy to clipboard
- **OCR Settings**: Configure language and auto-read behavior in Advanced Settings
- **High Accuracy**: Uses advanced LSTM-based recognition for better results
- **Privacy-First**: All OCR processing happens locally in your browser

**OCR Features:**
- Context menu integration for quick access
- Visual progress notifications
- Confidence score display
- Copy to clipboard functionality
- Optional auto-read extracted text
- Modal display for reviewing extracted text

## Version 2.0.0 - Feature Update

### 🎉 New Features

#### Context Menu Integration
- **Right-click to Read**: Right-click on selected text and choose "Read with Mockingbird"
- **Quick Page Reading**: Right-click anywhere and choose "Read entire page"
- **Save to Library**: Right-click to quickly save any page to your library

#### Click-to-Listen
- **Click Any Paragraph**: Click on any paragraph, heading, or list item to start reading from that point forward
- Visual feedback when clicking readable elements
- Intelligently continues reading through the rest of the article

#### Smart Content Extraction
Enhanced text extraction for popular websites:
- **Google Docs**: Special handling for Google Docs documents
- **Wikipedia**: Removes navigation, references, info boxes, and table of contents
- **Reddit**: Extracts post content from both old and new Reddit
- **Medium**: Optimized article extraction
- **Twitter/X**: Extract tweets and tweet threads
- **LinkedIn**: Extract posts and articles
- **Substack**: Newsletter content extraction
- **GitHub**: README files, issues, and pull request descriptions
- **PDF Support**: Basic PDF text extraction
- **News Sites**: Improved detection of article content
- **Standard Sites**: Expanded content selectors with 20+ common patterns
- **Smart Filtering**: Removes ads, comments, social buttons, navigation, and 30+ unwanted element types automatically

#### Advanced Playback Navigation
- **Time-based Skip**: Skip forward/backward 10 seconds with `Alt+Left` and `Alt+Right`
- **Jump to Percentage**: Quick buttons to jump to 0%, 25%, 50%, or 75% through the article
- Better sentence navigation for longer content

#### Reading Progress & Sleep Timer
- **Sleep Timer**: Set automatic stop timer for 5, 10, 15, 30, or 60 minutes
- Perfect for falling asleep to audiobooks or articles
- Visual notifications when timer is set and when it expires

#### Library & Reading History
- **Save Pages**: Save any webpage to your personal library
- **Reading Progress**: Automatically tracks where you left off
- **Resume Reading**: Continue reading from your saved position
- **Library Management**: View, open, and remove saved pages
- Shows save date and reading progress for each item

#### Auto-Scroll Control
- **Toggle Auto-Scroll**: Turn automatic scrolling on or off
- Follows highlighted text as it reads
- Smooth scrolling animation
- Preference saved across sessions

#### Enhanced UI
- New feature buttons for skip forward/backward
- Jump controls for quick navigation
- Library counter badge
- Sleep timer selector
- Modal library viewer
- Improved keyboard shortcuts display
- Helpful tips in the footer

### 🔧 Technical Improvements
- Better message passing between background and content scripts
- Improved state management for reading position
- Enhanced error handling
- Optimized performance for long articles
- Better compatibility with different website structures

### ⌨️ New Keyboard Shortcuts
- `Alt+→` - Skip forward 10 seconds
- `Alt+←` - Skip backward 10 seconds
- All shortcuts now displayed in the side panel

### 📚 Documentation Updates
- Updated README with all new features
- Added usage examples for new functionality
- Included tips for best experience

---

## Installation Instructions

To update to this version:
1. Navigate to `chrome://extensions/`
2. Click "Remove" on the old Mockingbird extension
3. Click "Load unpacked" and select the updated `integrations/Mockingbird_extension` folder
4. All your settings will be preserved!

## Compatibility
- Requires Piper TTS Server v1.0 or higher
- Chrome/Edge version 109 or higher
- Works with all existing voice models

## Coming Soon
- Voice typing/dictation feature
- More smart site integrations
- Custom highlighting styles
- Export/import library

---

Enjoy the enhanced Mockingbird experience! 🎧
