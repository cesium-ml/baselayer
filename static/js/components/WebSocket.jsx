import React from 'react';
import PropTypes from 'prop-types';
import { connect } from 'react-redux';
import { createCookie, readCookie, eraseCookie } from '../cookies';
import ReconnectingWebSocket from '../reconnecting-websocket';
import messageHandler, { MessageHandler } from '../MessageHandler';
import { showNotification, hideNotificationByTag, MS_PER_YEAR } from './Notifications';


function getTime() {
  const date = new Date();
  const n = date.toDateString();
  return date.toLocaleTimeString();
}


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
  return new Promise(
    (resolve, reject) => {
      // First, try and read the authentication token from a cookie
      const cookie_token = readCookie('auth_token');

      if (cookie_token) {
        resolve(cookie_token);
      } else {
        fetch(auth_url, {
          credentials: 'same-origin'
        })
          .then(checkStatus)
          .then(parseJSON)
          .then((json) => {
            const token = json.data.token;
            createCookie('auth_token', token);
            resolve(token);
          })
          .catch((error) => {
            // If we get a gateway error, it probably means nginx is
            // being restarted. Not much we can do, other than wait a
            // bit and continue with a fake token.
            const no_token = "no_auth_token_user bad_token";
            setTimeout(() => { resolve(no_token); }, 1000);
          });
      }
    }
  );
}


function showWebsocketNotification(dispatch, msg, tag) {
  dispatch(hideNotificationByTag(tag))
  .then(dispatch(showNotification(msg, 'warning', 50 * MS_PER_YEAR, tag)));
}


function clearWebsocketNotification(dispatch, tag) {
  dispatch(hideNotificationByTag(tag));
}


class WebSocket extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      connected: false,
      authenticated: false
    };

    const ws = new ReconnectingWebSocket(props.url);
    const tag = 'websocket';

    ws.onopen = (event) => {
      this.setState({ connected: true });
      clearWebsocketNotification(this.props.dispatch, tag);
    };

    ws.onerror = (event) => {
      showWebsocketNotification(
        this.props.dispatch,
        "No WebSocket connection: limited functionality may be available",
        tag
      );
    };

    ws.onmessage = (event) => {
      const data = event.data;

      // Ignore heartbeat signals
      if (data === '<3') {
        return;
      }

      const message = JSON.parse(data);
      const { actionType, payload } = message;

      switch (actionType) {
        case "AUTH REQUEST":
          getAuthToken(this.props.auth_url)
            .then(token => ws.send(token));
          break;
        case "AUTH FAILED":
          this.setState({ authenticated: false });
          eraseCookie('auth_token');
          showWebsocketNotification(
            this.props.dispatch,
            "WebSocket connection authentication failed: limited functionality may be available",
            tag
          );
          break;
        case "AUTH OK":
          this.setState({ authenticated: true });
          this.props.dispatch(hideNotificationByTag(tag));
          break;
        default:
          messageHandler.handle(actionType, payload);
      }
    };

    ws.onclose = (event) => {
      this.setState({ connected: false,
                     authenticated: false });
      showWebsocketNotification(
         this.props.dispatch,
         "No WebSocket connection: limited functionality may be available",
         tag
      );
    };
  }

  render() {
    let statusColor;
    if (!this.state.connected) {
      statusColor = 'red';
    } else {
      statusColor = this.state.authenticated ? 'lightgreen' : 'orange';
    }

    const statusSize = 12;

    const statusStyle = {
      display: 'inline-block',
      padding: 0,
      lineHeight: statusSize,
      textAlign: 'center',
      whiteSpace: 'nowrap',
      verticalAlign: 'baseline',
      backgroundColor: statusColor,
      borderRadius: '50%',
      border: '2px solid gray',
      position: 'relative',
      height: statusSize,
      width: statusSize
    };

    const connected_desc = (`WebSocket is
      ${(this.state.connected ? 'connected' : 'disconnected')} &
      ${(this.state.authenticated ? 'authenticated' : 'unauthenticated')}.`);
    return (
      <div
        id="websocketStatus"
        title={connected_desc}
        style={statusStyle}
      />
    );
  }
}

WebSocket.propTypes = {
  url: PropTypes.string.isRequired,
  auth_url: PropTypes.string.isRequired,
  messageHandler: PropTypes.shape({
    handle: PropTypes.func.isRequired
  })
};

module.exports = WebSocket;
