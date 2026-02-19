
const piperHost = {
  serviceReadyTopic: {
    callbacks: new Set(),
    publish() {
      for (const callback of this.callbacks) callback()
      this.callbacks.clear()
    },
    subscribeOnce(callback) {
      this.callbacks.add(callback)
    }
  },
  async ready({requestFocus}) {
    try {
      if (!await this.sendRequest("areYouThere", {requestFocus})) throw new Error("Absent")
    }
    catch (err) {
      await chrome.tabs.create({url: "index.html?showTest=1", pinned: true, active: requestFocus})
      await new Promise(f => this.serviceReadyTopic.subscribeOnce(f))
    }
  },
  async sendRequest(method, args) {
    const {error, result} = await chrome.runtime.sendMessage({
      to: "piper-host",
      type: "request",
      id: String(Math.random()),
      method,
      args
    })
    return error ? Promise.reject(error) : result
  }
}



//process messages from piper-host

importScripts("message-dispatcher.js")

const extDispatcher = makeDispatcher("service-worker", {
  piperServiceReady() {
    piperHost.serviceReadyTopic.publish()
  },
  onStart({speechId}) {
    chrome.ttsEngine.sendTtsEvent(speechId, {type: "start"})
  },
  onSentence({speechId, startIndex, endIndex}) {
    chrome.ttsEngine.sendTtsEvent(speechId, {type: "sentence", charIndex: startIndex, length: endIndex-startIndex})
  },
  onEnd({speechId}) {
    chrome.ttsEngine.sendTtsEvent(speechId, {type: "end"})
  },
  onError({speechId, error}) {
    chrome.ttsEngine.sendTtsEvent(speechId, {type: "error", errorMessage: error.message})
  }
})

chrome.runtime.onMessage.addListener(extDispatcher.dispatch)



//extension button action

chrome.action.onClicked.addListener(() => {
  piperHost.ready({requestFocus: true})
    .catch(console.error)
})

chrome.runtime.onInstalled.addListener(details => {
  if (details.reason == "install") {
    piperHost.ready({requestFocus: true})
      .catch(console.error)
  }
})



//ttsEngine commands

chrome.ttsEngine.onSpeak.addListener(async (utterance, options, sendTtsEvent) => {
  try {
    const speechId = await new Promise((fulfill, reject) => {
      const tmp = chrome.ttsEngine.sendTtsEvent
      const timeout = setTimeout(() => {
        chrome.ttsEngine.sendTtsEvent = tmp
        reject(new Error("Timeout getting speechId"))
      }, 5000)
      chrome.ttsEngine.sendTtsEvent = function(requestId) {
        clearTimeout(timeout)
        chrome.ttsEngine.sendTtsEvent = tmp
        fulfill(requestId)
      }
      sendTtsEvent({type: "dummy"})
    })
    console.debug("speechId", speechId)
    await piperHost.ready({requestFocus: false})
    await piperHost.sendRequest("speak", {speechId, utterance, ...options})
  }
  catch (err) {
    console.error(err)
    sendTtsEvent({type: "error", errorMessage: err.message || String(err)})
  }
})

chrome.ttsEngine.onPause.addListener(() => {
  Promise.race([
    piperHost.sendRequest("pause"),
    new Promise((_, reject) => setTimeout(() => reject(new Error("Pause timeout")), 5000))
  ]).catch(console.error)
})

chrome.ttsEngine.onResume.addListener(() => {
  Promise.race([
    piperHost.sendRequest("resume"),
    new Promise((_, reject) => setTimeout(() => reject(new Error("Resume timeout")), 5000))
  ]).catch(console.error)
})

chrome.ttsEngine.onStop.addListener(() => {
  Promise.race([
    piperHost.sendRequest("stop"),
    new Promise((_, reject) => setTimeout(() => reject(new Error("Stop timeout")), 5000))
  ]).catch(console.error)
})
