/**
 * @OnlyCurrentDoc
 *
 * Piper Speak Google Docs Add-on
 */

function onOpen(e) {
  DocumentApp.getUi().createAddonMenu()
      .addItem('Open Piper Speak', 'showSidebar')
      .addToUi();
}

function onInstall(e) {
  onOpen(e);
}

function showSidebar() {
  const html = HtmlService.createTemplateFromFile('Sidebar')
      .evaluate()
      .setTitle('Piper Speak')
      .setWidth(300);
  DocumentApp.getUi().showSidebar(html);
}

/**
 * Gets the selected text or the entire document text.
 */
function getSelectedText() {
  const selection = DocumentApp.getActiveDocument().getSelection();
  if (selection) {
    const elements = selection.getSelectedElements();
    let text = '';
    for (let i = 0; i < elements.length; i++) {
        const element = elements[i].getElement();
        if (element.asText) {
            text += element.asText().getText() + '\n';
        }
    }
    if (text.trim().length > 0) return text.trim();
  }
  
  // Fallback to whole body
  return DocumentApp.getActiveDocument().getBody().getText();
}

/**
 * Gets document metadata
 */
function getDocInfo() {
  const doc = DocumentApp.getActiveDocument();
  return {
    title: doc.getName(),
    url: doc.getUrl()
  };
}

/**
 * Gets document text split into sentences with positions (optimized)
 * Returns {text, paraIndex, startOffset, endOffset}
 */
function getSentencesWithPositions() {
  const doc = DocumentApp.getActiveDocument();
  const body = doc.getBody();
  const numChildren = body.getNumChildren();
  
  const result = [];
  
  for (let i = 0; i < numChildren; i++) {
    const child = body.getChild(i);
    const type = child.getType();
    
    // Process Paragraphs and ListItems (both contain text)
    if (type === DocumentApp.ElementType.PARAGRAPH || type === DocumentApp.ElementType.LIST_ITEM) {
      const element = (type === DocumentApp.ElementType.PARAGRAPH) ? child.asParagraph() : child.asListItem();
      const text = element.getText();
      
      if (!text.trim()) continue;
      
      // Match sentences: Non-punctuation followed by punctuation OR end of string
      const matches = text.match(/[^.!?]+(?:[.!?]+|$)/g);
      
      if (matches) {
        let currentPos = 0;
        matches.forEach(m => {
          if (m.trim()) {
            const trimmed = m.trim();
            const startInMatch = m.indexOf(trimmed);
            const absoluteStart = currentPos + startInMatch;
            const absoluteEnd = absoluteStart + trimmed.length;
            
            result.push({
              text: trimmed,
              paraIndex: i,
              startOffset: absoluteStart,
              endOffset: absoluteEnd
            });
          }
          currentPos += m.length;
        });
      }
    }
  }
  
  return result;
}

/**
 * Highlights text using direct paragraph access (O(1)) instead of searching
 */
function highlightTextRange(paraIndex, startOffset, endOffset) {
  try {
    const doc = DocumentApp.getActiveDocument();
    const body = doc.getBody();
    
    if (paraIndex == null || paraIndex >= body.getNumChildren()) return false;
    
    const child = body.getChild(paraIndex);
    const type = child.getType();
    let textElement;
    
    if (type === DocumentApp.ElementType.PARAGRAPH) {
      textElement = child.asParagraph().editAsText();
    } else if (type === DocumentApp.ElementType.LIST_ITEM) {
      textElement = child.asListItem().editAsText();
    } else {
      return false;
    }
    
    const rangeBuilder = doc.newRange();
    // addElement takes inclusive end offset
    rangeBuilder.addElement(textElement, startOffset, endOffset - 1);
    doc.setSelection(rangeBuilder.build());
    return true;
  } catch (e) {
    Logger.log('Error highlighting: ' + e.toString());
    return false;
  }
}

/**
 * Clears the current selection
 */
function clearSelection() {
  try {
    const doc = DocumentApp.getActiveDocument();
    const cursor = doc.getCursor();
    if (cursor) {
      doc.setCursor(cursor);
    }
    return true;
  } catch (e) {
    return false;
  }
}
