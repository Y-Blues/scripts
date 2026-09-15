from ycappuccino.api.decorators import Item, Property
from ycappuccino.api.models import Model


@Item(collection="scripts", name="script", plural="scripts", secure_read=True, secure_write=True)
class Script(Model):

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._name = None
        self._source = None

    @Property(name="name")
    def name(self, a_value):
        self._name = a_value

    @Property(name="source")
    def source(self, a_value):
        self._source = a_value
