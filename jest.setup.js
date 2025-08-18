// Polyfill for jsdom: HTMLFormElement.requestSubmit (not implemented)
if (!HTMLFormElement.prototype.requestSubmit) {
  Object.defineProperty(HTMLFormElement.prototype, 'requestSubmit', {
    configurable: true,
    value: function requestSubmit(submitter) {
      if (submitter) this._lastSubmitter = submitter; // optional
      // Fall back to regular submit; in tests we don't actually navigate.
      this.submit();
    }
  });
}
