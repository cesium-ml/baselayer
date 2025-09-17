import React from "react";
import { useDispatch, useSelector } from "react-redux";

export const SHOW_NOTIFICATION = "baselayer/SHOW_NOTIFICATION";
export const HIDE_NOTIFICATION = "baselayer/HIDE_NOTIFICATION";
export const HIDE_NOTIFICATION_BY_TAG = "baselayer/HIDE_NOTIFICATION_BY_TAG";

export const MS_PER_YEAR = 31540000000;

export function hideNotification(id) {
  return {
    type: HIDE_NOTIFICATION,
    payload: { id },
  };
}

export function hideNotificationByTag(tag) {
  return (dispatch) => {
    dispatch({
      type: HIDE_NOTIFICATION_BY_TAG,
      payload: { tag },
    });
    return Promise.resolve();
  };
}

export function Notifications() {
  const style = {
    position: "fixed",
    zIndex: 20000,
    top: "4.5em",
    width: "30em",
    right: "1em",
    overflow: "hidden",

    note: {
      color: "white",
      fontWeight: 600,
      padding: "1.3em",
      marginBottom: "0.5em",
      width: "100%",
      borderRadius: "8px",
      WebkitBoxShadow: "0 4px 5px rgba(0, 0, 0, 0.2)",
      MozBoxShadow: "0 4px 5px rgba(0, 0, 0, 0.2)",
      boxShadow: "0 4px 5px rgba(0, 0, 0, 0.2)",
      fontSize: "0.95rem",
      display: "inline-block",
    },
  };

  const noteColor = {
    error: "rgba(244,67,54,0.95)",
    warning: "rgba(255,152,0,0.95)",
    info: "rgba(11,181,119,0.95)",
  };

  const dispatch = useDispatch();
  const notifications = useSelector((state) => state.notifications.notes);

  return (
    notifications.length > 0 && (
      <div style={style}>
        {notifications.map((notification) => (
          <div
            data-testid={`notification-${notification.id}`}
            key={notification.id}
            onClick={() => dispatch(hideNotification(notification.id))}
            role="button"
            style={{ ...style.note, background: noteColor[notification.type] }}
            tabIndex="0"
          >
            {notification.note}
          </div>
        ))}
      </div>
    )
  );
}

let nextNotificationId = 0;
export function showNotification(
  note,
  type = "info",
  duration = 3000,
  tag = "default",
) {
  const thisId = nextNotificationId;
  nextNotificationId += 1;

  if (type === "error") {
    // eslint-disable-next-line no-console
    console.error(note);
  }

  return (dispatch) => {
    dispatch({
      type: SHOW_NOTIFICATION,
      payload: {
        id: thisId,
        note,
        type,
        tag,
      },
    });
    setTimeout(() => dispatch(hideNotification(thisId)), duration);
  };
}

export function reducer(state = { notes: [] }, action) {
  switch (action.type) {
    case SHOW_NOTIFICATION: {
      const { id, note, type, tag } = action.payload;
      return {
        notes: state.notes.concat({ id, note, type, tag }),
      };
    }
    case HIDE_NOTIFICATION:
      return {
        notes: state.notes.filter((n) => n.id !== action.payload.id),
      };
    case HIDE_NOTIFICATION_BY_TAG:
      return {
        notes: state.notes.filter((n) => n.tag !== action.payload.tag),
      };
    default:
      return state;
  }
}
