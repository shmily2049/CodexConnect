"""Wait for asynchronous model reads while pumping the actual Tk event loop."""
import time


def wait_profiles(app, timeout=10):
    deadline = time.monotonic() + timeout
    while app.profile_loading or app.profile_worker_running or app.busy:
        app.root.update()
        if time.monotonic() >= deadline:
            raise AssertionError('Model-list read did not finish')
        time.sleep(.005)
    app.root.update()
