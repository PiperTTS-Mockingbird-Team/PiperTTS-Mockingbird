// Mockingbird OCR Capture Module
// Handles screenshot selection and capture for OCR processing

console.log('[Mockingbird OCR] Capture module loaded');

class OCRCaptureOverlay {
  constructor() {
    this.overlay = null;
    this.selectionBox = null;
    this.instructionsBox = null;
    this.startX = 0;
    this.startY = 0;
    this.isSelecting = false;
    this.isActive = false;
    
    this.boundHandleMouseDown = this.handleMouseDown.bind(this);
    this.boundHandleMouseMove = this.handleMouseMove.bind(this);
    this.boundHandleMouseUp = this.handleMouseUp.bind(this);
    this.boundHandleKeyDown = this.handleKeyDown.bind(this);
  }
  
  activate() {
    if (this.isActive) return;
    
    console.log('[Mockingbird OCR] Activating capture overlay');
    this.isActive = true;
    
    // Inject CSS if not already present
    if (!document.getElementById('Mockingbird-ocr-styles')) {
      const link = document.createElement('link');
      link.id = 'Mockingbird-ocr-styles';
      link.rel = 'stylesheet';
      link.href = chrome.runtime.getURL('content/ocr-capture.css');
      document.head.appendChild(link);
    }
    
    // Create overlay
    this.overlay = document.createElement('div');
    this.overlay.className = 'Mockingbird-ocr-overlay';
    
    // Create instructions
    this.instructionsBox = document.createElement('div');
    this.instructionsBox.className = 'Mockingbird-ocr-instructions';
    this.instructionsBox.innerHTML = `
        <strong>📝 OCR Text Capture</strong><br>
        Drag to select text area • Press <kbd>Esc</kbd> to cancel<br>
        <small style="opacity: 0.8;">⚠ Select clear, readable text for best results</small>
    `;
    
    document.body.appendChild(this.overlay);
    document.body.appendChild(this.instructionsBox);
    
    // Add event listeners
    this.overlay.addEventListener('mousedown', this.boundHandleMouseDown);
    document.addEventListener('mousemove', this.boundHandleMouseMove);
    document.addEventListener('mouseup', this.boundHandleMouseUp);
    document.addEventListener('keydown', this.boundHandleKeyDown);
    
    // Prevent page scrolling
    document.body.style.overflow = 'hidden';
  }
  
  deactivate() {
    if (!this.isActive) return;
    
    console.log('[Mockingbird OCR] Deactivating capture overlay');
    this.isActive = false;
    this.isSelecting = false;
    
    // Remove event listeners
    if (this.overlay) {
      this.overlay.removeEventListener('mousedown', this.boundHandleMouseDown);
    }
    document.removeEventListener('mousemove', this.boundHandleMouseMove);
    document.removeEventListener('mouseup', this.boundHandleMouseUp);
    document.removeEventListener('keydown', this.boundHandleKeyDown);
    
    // Remove elements
    if (this.overlay && this.overlay.parentNode) {
      this.overlay.parentNode.removeChild(this.overlay);
    }
    if (this.selectionBox && this.selectionBox.parentNode) {
      this.selectionBox.parentNode.removeChild(this.selectionBox);
    }
    if (this.instructionsBox && this.instructionsBox.parentNode) {
      this.instructionsBox.parentNode.removeChild(this.instructionsBox);
    }
    
    this.overlay = null;
    this.selectionBox = null;
    this.instructionsBox = null;
    
    // Restore page scrolling
    document.body.style.overflow = '';
  }
  
  handleMouseDown(e) {
    if (e.button !== 0) return; // Only left click
    
    this.isSelecting = true;
    this.startX = e.clientX + window.scrollX;
    this.startY = e.clientY + window.scrollY;
    
    // Create selection box
    if (!this.selectionBox) {
      this.selectionBox = document.createElement('div');
      this.selectionBox.className = 'Mockingbird-ocr-selection';
      document.body.appendChild(this.selectionBox);
    }
    
    this.selectionBox.style.left = `${this.startX}px`;
    this.selectionBox.style.top = `${this.startY}px`;
    this.selectionBox.style.width = '0px';
    this.selectionBox.style.height = '0px';
    
    e.preventDefault();
    e.stopPropagation();
  }
  
  handleMouseMove(e) {
    if (!this.isSelecting || !this.selectionBox) return;
    
    const currentX = e.clientX + window.scrollX;
    const currentY = e.clientY + window.scrollY;
    
    const left = Math.min(this.startX, currentX);
    const top = Math.min(this.startY, currentY);
    const width = Math.abs(currentX - this.startX);
    const height = Math.abs(currentY - this.startY);
    
    this.selectionBox.style.left = `${left}px`;
    this.selectionBox.style.top = `${top}px`;
    this.selectionBox.style.width = `${width}px`;
    this.selectionBox.style.height = `${height}px`;
    
    // Show dimensions in the selection box
    const sizeText = `${Math.round(width)} × ${Math.round(height)}px`;
    const quality = (width >= 200 && height >= 40) ? '✓ Good size' : 
                   (width >= 100 && height >= 30) ? '⚠ Small' : 
                   '❌ Too small';
    this.selectionBox.setAttribute('data-size', `${sizeText} - ${quality}`);
  }
  
  async handleMouseUp(e) {
    if (!this.isSelecting) return;
    
    this.isSelecting = false;
    
    const currentX = e.clientX + window.scrollX;
    const currentY = e.clientY + window.scrollY;
    
    const left = Math.min(this.startX, currentX);
    const top = Math.min(this.startY, currentY);
    const width = Math.abs(currentX - this.startX);
    const height = Math.abs(currentY - this.startY);
    
    // Check minimum size (at least 20x20 pixels)
    if (width < 20 || height < 20) {
      console.log('[Mockingbird OCR] Selection too small, canceling');
      this.showErrorFeedback('Selection too small - please select a larger area');
      setTimeout(() => this.deactivate(), 2000);
      return;
    }
    
    // Warn if very small (might not contain readable text)
    if (width < 100 || height < 30) {
      console.warn(`[Mockingbird OCR] Small selection: ${width}x${height} - may not detect text`);
    }
    
    // Show processing feedback
    this.showProcessingFeedback();
    
    try {
      // Capture the selected area
      console.log(`[Mockingbird OCR] Capturing area: ${width}x${height} at (${left}, ${top})`);
      await this.captureSelection(left, top, width, height);
      // Don't deactivate here - showResultsIframe handles it
    } catch (error) {
      console.error('[Mockingbird OCR] Capture failed:', error);
      this.showErrorFeedback(error.message || 'Capture failed');
      // Auto-close after 5 seconds
      setTimeout(() => this.deactivate(), 5000);
    }
  }
  
  handleKeyDown(e) {
    if (e.key === 'Escape') {
      console.log('[Mockingbird OCR] Canceled by user');
      this.deactivate();
    }
  }
  
  showProcessingFeedback() {
    if (this.instructionsBox) {
      this.instructionsBox.innerHTML = '⏳ Processing OCR...';
      this.instructionsBox.style.backgroundColor = 'rgba(59, 130, 246, 0.9)';
    }
  }
  
  showErrorFeedback(message) {
    if (this.instructionsBox) {
      this.instructionsBox.innerHTML = `❌ ${message}<br><small>Press Esc to close or try again</small>`;
      this.instructionsBox.style.backgroundColor = 'rgba(239, 68, 68, 0.9)';
    }
  }
  
  async captureSelection(left, top, width, height) {
    try {
      // Hide the size indicator before capturing
      if (this.selectionBox) {
        this.selectionBox.classList.add('capturing');
      }
      
      // Small delay to ensure CSS change is applied
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Request tab capture from background script
      const response = await chrome.runtime.sendMessage({
        type: 'OCR_CAPTURE',
        selection: {
          left: left - window.scrollX,
          top: top - window.scrollY,
          width,
          height,
          dpr: window.devicePixelRatio || 1,
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight
        }
      });
      
      if (!response.success) {
        throw new Error(response.error || 'Capture failed');
      }
      
      console.log('[Mockingbird OCR] Capture successful');
      
      // Save result to storage so the side panel (and future UI) can read it
      await chrome.storage.local.set({
        lastOcrResult: {
          text: response.text,
          image: response.image,
          confidence: response.confidence,
          success: true
        }
      });

      // Close overlay; side panel displays OCR_RESULT.
      this.deactivate();

    } catch (error) {
      console.error('[Mockingbird OCR] Error capturing selection:', error);
      // Remove capturing class on error
      if (this.selectionBox) {
        this.selectionBox.classList.remove('capturing');
      }
      throw error;
    }
  }

  showResultsIframe() {
    // Remove existing instructions
    if (this.instructionsBox) {
      this.instructionsBox.style.display = 'none';
    }
    
    // Create iframe
    const iframe = document.createElement('iframe');
    iframe.src = chrome.runtime.getURL('content/ocr-result.html');
    iframe.className = 'Mockingbird-ocr-result-iframe';
    iframe.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        border: none;
        z-index: 2147483650;
        background: rgba(0,0,0,0.5);
    `;
    
    document.body.appendChild(iframe);
    this.resultIframe = iframe;
    
    // Listen for messages from iframe
    window.addEventListener('message', this.handleIframeMessage.bind(this));
  }
  
  handleIframeMessage(event) {
      if (event.data.type === 'Mockingbird_OCR_CLOSE') {
          this.closeResults();
      } else if (event.data.type === 'Mockingbird_OCR_RETRY') {
          this.closeResults();
          this.retryCapture();
      }
  }
  
  closeResults() {
      if (this.resultIframe) {
          this.resultIframe.remove();
          this.resultIframe = null;
      }
      this.deactivate();
  }
  
  retryCapture() {
      // Reset selection box visuals
      if (this.selectionBox) { // Re-init if needed
          this.selectionBox.style.width = '0px';
          this.selectionBox.style.height = '0px';
      }
      this.isSelecting = false;
      
      // Restore instructions
      if (this.instructionsBox) {
           this.instructionsBox.innerHTML = 'Drag to select area for OCR • Press <kbd>Esc</kbd> to cancel';
           this.instructionsBox.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
           this.instructionsBox.style.display = 'block';
      }
      
      if (!this.isActive) this.activate();
  }
}

// Create and export OCR capture instance
window.MockingbirdOCR = new OCRCaptureOverlay();

// Listen for activation messages
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'ACTIVATE_OCR_CAPTURE') {
    window.MockingbirdOCR.activate();
    sendResponse({ success: true });
  }
  
  if (message.type === 'DEACTIVATE_OCR_CAPTURE') {
    window.MockingbirdOCR.deactivate();
    sendResponse({ success: true });
  }
});

console.log('[Mockingbird OCR] Capture module ready');
