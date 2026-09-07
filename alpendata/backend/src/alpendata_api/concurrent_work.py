"""Bounded chat concurrency; shutdown drains admitted work before closing the DB."""

from concurrent.futures import ThreadPoolExecutor


class ConcurrentWork:
    def __init__(self, step, slots=3):
        self.step, self.slots = step, slots
        self.executor = ThreadPoolExecutor(max_workers=slots, thread_name_prefix="alpendata-chat")
        self.pending = []

    def tick(self):
        pending = []
        for future in self.pending:
            if future.done():
                future.result()
            else:
                pending.append(future)
        self.pending = pending
        if len(self.pending) < self.slots:
            self.pending.append(self.executor.submit(self.step))
        return bool(self.pending)

    def close(self):
        self.executor.shutdown(wait=True)
        for future in self.pending:
            future.result()


class WorkspaceWork:
    """Keep a parser slot available even while every chat slot is occupied."""

    def __init__(self, chat, documents):
        self.chat = ConcurrentWork(chat)
        self.documents = ConcurrentWork(documents, slots=1)

    def tick(self):
        chat = self.chat.tick()
        documents = self.documents.tick()
        return chat or documents

    def close(self):
        try:
            self.chat.close()
        finally:
            self.documents.close()
