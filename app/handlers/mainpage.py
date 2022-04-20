from baselayer.app.handlers.base import BaseHandler


class MainPageHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.render("login.html")
        else:
            self.render("index.html")
