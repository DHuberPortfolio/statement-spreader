import { Component, type ErrorInfo, type ReactNode } from "react";

/** One broken screen shows a message and a way out, never a blank page. Reset by giving it a new key on navigation. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  override render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="state state-error" role="alert">
        <h2>This page hit a problem</h2>
        <p>Nothing was lost: your work is saved on the server. Reload the page, or go back to the overview.</p>
        <div className="form-row">
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload
          </button>
          <a className="btn" href="/">
            Overview
          </a>
        </div>
      </div>
    );
  }
}
