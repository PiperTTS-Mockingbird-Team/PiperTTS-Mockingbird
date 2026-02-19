
let piperService
let speechId


//handle messages from piper-service

const domDispatcher = makeDispatcher("piper-host", {
  advertiseVoices({voices}, sender) {
    chrome.ttsEngine.updateVoices(voices)
    piperService = sender
    notifyServiceWorker("piperServiceReady")
  },
  onStart(args) {
    notifyServiceWorker("onStart", {...args, speechId})
  },
  onSentence(args) {
    notifyServiceWorker("onSentence", {...args, speechId})
  },
  onEnd(args) {
    notifyServiceWorker("onEnd", {...args, speechId})
  },
  onError(args) {
    notifyServiceWorker("onError", {...args, speechId})
  }
})

window.addEventListener("message", event => {
  // Validate origin - only accept messages from the iframe source
  const allowedOrigin = "https://piper.ttstool.com"
  if (event.origin !== allowedOrigin) {
    console.warn("Ignoring message from unauthorized origin:", event.origin)
    return
  }
  
  const send = message => event.source.postMessage(message, {targetOrigin: event.origin})
  const sender = {
    sendRequest(method, args) {
      const id = String(Math.random())
      send({to: "piper-service", type: "request", id, method, args})
      return domDispatcher.waitForResponse(id)
    }
  }
  domDispatcher.dispatch(event.data, sender, send)
})


//handle messages from extension service worker

const extDispatcher = makeDispatcher("piper-host", {
  async areYouThere({requestFocus}) {
    if (requestFocus) {
      const tab = await chrome.tabs.getCurrent()
      await Promise.all([
        chrome.windows.update(tab.windowId, {focused: true}),
        chrome.tabs.update(tab.id, {active: true})
      ])
    }
    return true
  },
  speak(args) {
    if (!piperService) throw new Error("No service")
    speechId = args.speechId
    return piperService.sendRequest("speak", args)
  },
  pause(args) {
    if (!piperService) throw new Error("No service")
    return piperService.sendRequest("pause", args)
  },
  resume(args) {
    if (!piperService) throw new Error("No service")
    return piperService.sendRequest("resume", args)
  },
  stop(args) {
    if (!piperService) throw new Error("No service")
    return piperService.sendRequest("stop", args)
  }
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  return extDispatcher.dispatch(message, sender, res => {
    // Only serialize if error is an actual Error/DOMException object (not already serialized)
    if (res.error && typeof res.error === 'object' && res.error.constructor && 
        (res.error instanceof Error || res.error instanceof DOMException)) {
      res.error = {
        name: res.error.name,
        message: res.error.message,
        stack: res.error.stack
      }
    }
    sendResponse(res)
  })
})

function notifyServiceWorker(method, args) {
  chrome.runtime.sendMessage({
    to: "service-worker",
    type: "notification",
    method,
    args
  })
}
