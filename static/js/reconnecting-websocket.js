// MIT License:
//
// Copyright (c) 2010-2012, Joe Walnes
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

/**
 * This behaves like a WebSocket in every way, except if it fails to connect,
 * or it gets disconnected, it will repeatedly poll until it successfully connects
 * again.
 *
 * It is API compatible, so when you have:
 * ws = new WebSocket('ws://....');
 * you can replace with:
 * ws = new ReconnectingWebSocket('ws://....');
 *
 * The event stream will typically look like:
 * onconnecting
 * onopen
 * onmessage
 * onmessage
 * onclose // lost connection
 * onconnecting
 * onopen // sometime later...
 * onmessage
 * onmessage
 * etc...
 *
 * It is API compatible with the standard WebSocket API, apart from the following members:
 *
 * - `bufferedAmount`
 * - `extensions`
 * - `binaryType`
 *
 * Latest version: https://github.com/joewalnes/reconnecting-websocket/
 * - Joe Walnes
 *
 * Syntax
 * ======
 * var socket = new ReconnectingWebSocket(url, protocols, options);
 *
 * Parameters
 * ==========
 * url - The url you are connecting to.
 * protocols - Optional string or array of protocols.
 * options - See below
 *
 * Options
 * =======
 * Options can either be passed upon instantiation or set after instantiation:
 *
 * var socket = new ReconnectingWebSocket(url, null, { debug: true, reconnectInterval: 4000 });
 *
 * or
 *
 * var socket = new ReconnectingWebSocket(url);
 * socket.debug = true;
 * socket.reconnectInterval = 4000;
 *
 * debug
 * - Whether this instance should log debug messages. Accepts true or false. Default: false.
 *
 * automaticOpen
 * - Whether or not the websocket should attempt to connect immediately upon instantiation. The socket can be manually opened or closed at any time using ws.open() and ws.close().
 *
 * reconnectInterval
 * - The number of milliseconds to delay before attempting to reconnect. Accepts integer. Default: 1000.
 *
 * maxReconnectInterval
 * - The maximum number of milliseconds to delay a reconnection attempt. Accepts integer. Default: 30000.
 *
 * reconnectDecay
 * - The rate of increase of the reconnect delay. Allows reconnect attempts to back off when problems persist. Accepts integer or float. Default: 1.5.
 *
 * timeoutInterval
 * - The maximum time in milliseconds to wait for a connection to succeed before closing and retrying. Accepts integer. Default: 2000.
 *
 */

function ReconnectingWebSocket(url, protocols, options) {
  // Default settings
  const settings = {
    /** Whether this instance should log debug messages. */
    debug: false,

    /** Whether or not the websocket should attempt to connect immediately upon instantiation. */
    automaticOpen: true,

    /** The number of milliseconds to delay before attempting to reconnect. */
    reconnectInterval: 1000,

    /** The maximum number of milliseconds to delay a reconnection attempt. */
    maxReconnectInterval: 30000,

    /** The rate of increase of the reconnect delay. Allows reconnect attempts to back off when problems persist. */
    reconnectDecay: 1.5,

    /** The maximum time in milliseconds to wait for a connection to succeed before closing and retrying. */
    timeoutInterval: 2000,

    /** The maximum number of reconnection attempts to make. Unlimited if null. */
    maxReconnectAttempts: null,

    /** The binary type, possible values 'blob' or 'arraybuffer', default 'blob'. */
    binaryType: "blob",
  };

  if (!options) {
    options = {};
  }

  // Overwrite and define settings with options if they exist.
  for (const key in settings) {
    if (typeof options[key] === "undefined") {
      this[key] = settings[key];
    } else {
      this[key] = options[key];
    }
  }

  // These should be treated as read-only properties

  /** The URL as resolved by the constructor. This is always an absolute URL. Read only. */
  this.url = url;

  /** The number of attempted reconnects since starting, or the last successful connection. Read only. */
  this.reconnectAttempts = 0;

  /**
   * The current state of the connection.
   * Can be one of: WebSocket.CONNECTING, WebSocket.OPEN, WebSocket.CLOSING, WebSocket.CLOSED
   * Read only.
   */
  this.readyState = WebSocket.CONNECTING;

  /**
   * A string indicating the name of the sub-protocol the server selected; this will be one of
   * the strings specified in the protocols parameter when creating the WebSocket object.
   * Read only.
   */
  this.protocol = null;

  // Private state variables
  const that = this;
  let ws;
  let forcedClose = false;
  let timedOut = false;
  const eventTarget = document.createElement("div");

  // Wire up "on*" properties as event handlers
  eventTarget.addEventListener("open", (event) => {
    that.onopen(event);
  });
  eventTarget.addEventListener("close", (event) => {
    that.onclose(event);
  });
  eventTarget.addEventListener("connecting", (event) => {
    that.onconnecting(event);
  });
  eventTarget.addEventListener("message", (event) => {
    that.onmessage(event);
  });
  eventTarget.addEventListener("error", (event) => {
    that.onerror(event);
  });

  // Expose the API required by EventTarget
  this.addEventListener = eventTarget.addEventListener.bind(eventTarget);
  this.removeEventListener = eventTarget.removeEventListener.bind(eventTarget);
  this.dispatchEvent = eventTarget.dispatchEvent.bind(eventTarget);

  /**
   * This function generates an event that is compatible with standard
   * compliant browsers and IE9 - IE11
   *
   * This will prevent the error:
   * Object doesn't support this action
   *
   * http://stackoverflow.com/questions/19345392/why-arent-my-parameters-getting-passed-through-to-a-dispatched-event/19345563#19345563
   * @param s String The name that the event should use
   * @param args Object an optional object that the event will use
   */
  function generateEvent(s, args) {
    const evt = document.createEvent("CustomEvent");
    evt.initCustomEvent(s, false, false, args);
    return evt;
  }

  this.open = function (reconnectAttempt) {
    ws = new WebSocket(that.url, protocols || []);
    ws.binaryType = this.binaryType;

    if (reconnectAttempt) {
      if (
        this.maxReconnectAttempts &&
        this.reconnectAttempts > this.maxReconnectAttempts
      ) {
        return;
      }
    } else {
      eventTarget.dispatchEvent(generateEvent("connecting"));
      this.reconnectAttempts = 0;
    }

    if (that.debug || ReconnectingWebSocket.debugAll) {
      // eslint-disable-next-line no-console
      console.debug("ReconnectingWebSocket", "attempt-connect", that.url);
    }

    const localWs = ws;
    const timeout = setTimeout(() => {
      if (that.debug || ReconnectingWebSocket.debugAll) {
        // eslint-disable-next-line no-console
        console.debug("ReconnectingWebSocket", "connection-timeout", that.url);
      }
      timedOut = true;
      localWs.close();
      timedOut = false;
    }, that.timeoutInterval);

    ws.onopen = function (event) {
      clearTimeout(timeout);
      if (that.debug || ReconnectingWebSocket.debugAll) {
        // eslint-disable-next-line no-console
        console.debug("ReconnectingWebSocket", "onopen", that.url);
      }
      that.protocol = ws.protocol;
      that.readyState = WebSocket.OPEN;
      that.reconnectAttempts = 0;
      const e = generateEvent("open");
      e.isReconnect = reconnectAttempt;
      reconnectAttempt = false;
      eventTarget.dispatchEvent(e);
    };

    ws.onclose = function (event) {
      clearTimeout(timeout);
      ws = null;
      if (forcedClose) {
        that.readyState = WebSocket.CLOSED;
        eventTarget.dispatchEvent(generateEvent("close"));
      } else {
        that.readyState = WebSocket.CONNECTING;
        const e = generateEvent("connecting");
        e.code = event.code;
        e.reason = event.reason;
        e.wasClean = event.wasClean;
        eventTarget.dispatchEvent(e);

        if (!reconnectAttempt && !timedOut) {
          if (that.debug || ReconnectingWebSocket.debugAll) {
            // eslint-disable-next-line no-console
            console.debug("ReconnectingWebSocket", "onclose", that.url);
          }
          eventTarget.dispatchEvent(generateEvent("close"));
        }

        const reconnectDelay =
          that.reconnectInterval *
          that.reconnectDecay ** that.reconnectAttempts;
        setTimeout(
          () => {
            that.reconnectAttempts++;
            that.open(true);
          },
          reconnectDelay > that.maxReconnectInterval
            ? that.maxReconnectInterval
            : reconnectDelay,
        );
      }
    };

    ws.onmessage = function (event) {
      if (that.debug || ReconnectingWebSocket.debugAll) {
        // eslint-disable-next-line no-console
        console.debug(
          "ReconnectingWebSocket",
          "onmessage",
          that.url,
          event.data,
        );
      }
      const e = generateEvent("message");
      e.data = event.data;
      eventTarget.dispatchEvent(e);
    };

    ws.onerror = function (event) {
      if (that.debug || ReconnectingWebSocket.debugAll) {
        // eslint-disable-next-line no-console
        console.debug("ReconnectingWebSocket", "onerror", that.url, event);
      }
      eventTarget.dispatchEvent(generateEvent("error"));
    };
  };

  // Whether or not to create a websocket upon instantiation
  if (this.automaticOpen === true) {
    this.open(false);
  }

  /**
   * Transmits data to the server over the WebSocket connection.
   *
   * @param data a text string, ArrayBuffer or Blob to send to the server.
   */
  this.send = function (data) {
    if (ws) {
      if (that.debug || ReconnectingWebSocket.debugAll) {
        // eslint-disable-next-line no-console
        console.debug("ReconnectingWebSocket", "send", that.url, data);
      }
      return ws.send(data);
    }
    throw new DOMException("WebSocket is not open", "InvalidStateError");
  };

  /**
   * Closes the WebSocket connection or connection attempt, if any.
   * If the connection is already CLOSED, this method does nothing.
   */
  this.close = function (code, reason) {
    // Default CLOSE_NORMAL code
    if (typeof code === "undefined") {
      code = 1000;
    }
    forcedClose = true;
    if (ws) {
      ws.close(code, reason);
    }
  };

  /**
   * Additional public API method to refresh the connection if still open (close, re-open).
   * For example, if the app suspects bad data / missed heart beats, it can try to refresh.
   */
  this.refresh = function () {
    if (ws) {
      ws.close();
    }
  };
}

/**
 * An event listener to be called when the WebSocket connection's readyState changes to OPEN;
 * this indicates that the connection is ready to send and receive data.
 */
ReconnectingWebSocket.prototype.onopen = function (event) {
  /* no-op default, user-assigned */
};

/** An event listener to be called when the WebSocket connection's readyState changes to CLOSED. */
ReconnectingWebSocket.prototype.onclose = function (event) {
  /* no-op default, user-assigned */
};

/** An event listener to be called when a connection begins being attempted. */
ReconnectingWebSocket.prototype.onconnecting = function (event) {
  /* no-op default, user-assigned */
};

/** An event listener to be called when a message is received from the server. */
ReconnectingWebSocket.prototype.onmessage = function (event) {
  /* no-op default, user-assigned */
};

/** An event listener to be called when an error occurs. */
ReconnectingWebSocket.prototype.onerror = function (event) {
  /* no-op default, user-assigned */
};

/**
 * Whether all instances of ReconnectingWebSocket should log debug messages.
 * Setting this to true is the equivalent of setting all instances of ReconnectingWebSocket.debug to true.
 */
ReconnectingWebSocket.debugAll = false;

ReconnectingWebSocket.CONNECTING = WebSocket.CONNECTING;
ReconnectingWebSocket.OPEN = WebSocket.OPEN;
ReconnectingWebSocket.CLOSING = WebSocket.CLOSING;
ReconnectingWebSocket.CLOSED = WebSocket.CLOSED;

export default ReconnectingWebSocket;
