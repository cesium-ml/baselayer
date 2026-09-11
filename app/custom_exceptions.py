import tornado.web


class AccessError(tornado.web.HTTPError):
    def __init__(self, reason):
        super().__init__(reason=reason, status_code=400)

    def __str__(self):
        return self.reason
