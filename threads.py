import threading


class Threads:
    def __init__(self):
        self.thread_ids = set()
        self._lock = threading.Lock()

    def get_new_thread_id(self) -> int:
        i = 0
        with self._lock:
            while True:
                if i not in self.thread_ids:
                    self.thread_ids.add(i)
                    break
                i += 1
        return i

    def add_thread(self, thread_id: int):
        self.thread_ids.add(thread_id)

    def remove_thread(self, thread_id: int):
        self.thread_ids.remove(thread_id)


threads = Threads()
