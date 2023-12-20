import React from "react";
import PropTypes from "prop-types";
import { createCookie, readCookie, eraseCookie } from "../cookies";
import ReconnectingWebSocket from "../reconnecting-websocket";
import messageHandler from "../MessageHandler";
import {
  showNotification,
  hideNotificationByTag,
  MS_PER_YEAR,
} from "./Notifications";

function checkStatus(response) {
  if (response.status >= 200 && response.status < 300) {
    return response;
  } else {
    const error = new Error(response.statusText);
    error.response = response;
    throw error;
  }
}

function parseJSON(response) {
  return response.json();
}

function getAuthToken(auth_url) {
  return new Promise((resolve) => {
    // First, try and read the authentication token from a cookie
    const cookie_token = readCookie("auth_token");

    if (cookie_token) {
      resolve(cookie_token);
    } else {
      fetch(auth_url, {
        credentials: "same-origin",
      })
        .then(checkStatus)
        .then(parseJSON)
        .then((json) => {
          const { token } = json.data;
          createCookie("auth_token", token);
          resolve(token);
        })
        .catch(() => {
          // If we get a gateway error, it probably means nginx is
          // being restarted. Not much we can do, other than wait a
          // bit and continue with a fake token.
          const no_token = "no_auth_token_user bad_token";
          setTimeout(() => {
            resolve(no_token);
          }, 1000);
        });
    }
  });
}

function showWebsocketNotification(dispatch, msg, tag) {
  dispatch(hideNotificationByTag(tag)).then(
    dispatch(showNotification(msg, "warning", 50 * MS_PER_YEAR, tag)),
  );
}

function clearWebsocketNotification(dispatch, tag) {
  dispatch(hideNotificationByTag(tag));
}

class WebSocket extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      connected: false,
      authenticated: false,
    };

    const { url, auth_url, dispatch } = this.props;
    const ws = new ReconnectingWebSocket(url);
    const tag = "websocket";

    ws.onopen = () => {
      this.setState({ connected: true });
      clearWebsocketNotification(dispatch, tag);
    };

    ws.onerror = () => {
      showWebsocketNotification(
        dispatch,
        "No WebSocket connection: limited functionality may be available",
        tag,
      );
    };

    ws.onmessage = (event) => {
      const { data } = event;

      // Ignore heartbeat signals
      if (data === "<3") {
        return;
      }

      const message = JSON.parse(data);
      const { actionType, payload } = message;

      switch (actionType) {
        case "AUTH REQUEST":
          getAuthToken(auth_url).then((token) => ws.send(token));
          break;
        case "AUTH FAILED":
          this.setState({ authenticated: false });
          eraseCookie("auth_token");
          showWebsocketNotification(
            dispatch,
            "WebSocket connection authentication failed: limited functionality may be available",
            tag,
          );
          break;
        case "AUTH OK":
          this.setState({ authenticated: true });
          dispatch(hideNotificationByTag(tag));
          break;
        default:
          messageHandler.handle(actionType, payload);
      }
    };

    ws.onclose = () => {
      this.setState({
        connected: false,
        authenticated: false,
      });
      showWebsocketNotification(
        dispatch,
        "No WebSocket connection: limited functionality may be available",
        tag,
      );
    };
  }

  render() {
    const { connected, authenticated } = this.state;
    let statusColor;
    if (!connected) {
      statusColor = "red";
    } else {
      statusColor = authenticated ? "lightgreen" : "orange";
    }

    const statusSize = 12;

    const statusStyle = {
      display: "inline-block",
      padding: 0,
      lineHeight: statusSize,
      textAlign: "center",
      whiteSpace: "nowrap",
      verticalAlign: "baseline",
      backgroundColor: statusColor,
      borderRadius: "50%",
      border: "2px solid gray",
      position: "relative",
      height: statusSize,
      width: statusSize,
    };

    const connected_desc = `WebSocket is
      ${connected ? "connected" : "disconnected"} &
      ${authenticated ? "authenticated" : "unauthenticated"}.`;
    return (
      <div id="websocketStatus" title={connected_desc} style={statusStyle} />
    );
  }
}

WebSocket.propTypes = {
  url: PropTypes.string.isRequired,
  auth_url: PropTypes.string.isRequired,
  messageHandler: PropTypes.shape({
    handle: PropTypes.func.isRequired,
  }).isRequired,
  dispatch: PropTypes.func.isRequired,
};

export default WebSocket;
