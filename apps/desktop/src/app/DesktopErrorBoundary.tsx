import { Component, type ErrorInfo, type ReactNode } from "react";

interface DesktopErrorBoundaryProps {
  children: ReactNode;
}

interface DesktopErrorBoundaryState {
  hasError: boolean;
}

/**
 * Keeps a rendering failure fail-closed. A broken presentation cannot imply
 * that a task was submitted, completed, approved, or sent externally.
 */
export class DesktopErrorBoundary extends Component<DesktopErrorBoundaryProps, DesktopErrorBoundaryState> {
  state: DesktopErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): DesktopErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("AirBench desktop rendering failed", { errorName: error.name, componentStack: info.componentStack });
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="fatal-startup" role="alert">
          <div className="fatal-startup-card">
            <p className="eyebrow">AIRBENCH STARTUP BLOCKED</p>
            <h1>The workbench could not render safely</h1>
            <p>AirBench stopped this screen before submitting or changing any task. Restart the desktop application or contact your administrator with the application version.</p>
            <small data-testid="app-version">AirBench {__AIRBENCH_VERSION__} / offline shell</small>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
