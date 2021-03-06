from __future__ import absolute_import

from abc import abstractmethod

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal

from TriblerGUI.defs import ACTION_BUTTONS
from TriblerGUI.utilities import format_size, pretty_date


class RemoteTableModel(QAbstractTableModel):
    """
    The base model for the tables in the Tribler GUI.
    It is specifically designed to fetch data from a remote data source, i.e. over a RESTful API.
    """
    on_sort = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super(RemoteTableModel, self).__init__(parent)
        self.data_items = []
        self.item_load_batch = 50
        self.total_items = 0  # The total number of items without pagination

        # Unique identifier mapping for items. For torrents, it is infohash and for channels, it is concatenated value
        # of public key and channel id
        self.item_uid_map = {}

    @abstractmethod
    def get_item_uid(self, item):
        pass

    def reset(self):
        self.beginResetModel()
        self.data_items = []
        self.item_uid_map = {}
        self.total_items = 0
        self.endResetModel()

    def sort(self, column, order):
        self.reset()
        self.on_sort.emit(self.columns[column], bool(order))

    def add_items(self, new_items, remote=False):
        """
        Adds new items to the table model. All items are mapped to their unique ids to avoid the duplicates.
        If the new items are remote then the items are prepended to the top else appended to the end of the model.
        :param new_items: list(item)
        :param remote: True if new_items are received from remote peers else False for local items
        :return: None
        """
        if not new_items:
            return

        # Note: If we want to block the signal like itemChanged, we must use QSignalBlocker object

        # Only add unique items to the table model and reverse mapping from unique ids to rows is built.
        # If items are remote, prepend to the top else append to the end of the model.
        new_items_map = {}
        insert_index = len(self.data_items) if not remote else 0
        unique_items = []
        for item in new_items:
            item_uid = self.get_item_uid(item)

            if item_uid and item_uid not in self.item_uid_map:
                new_items_map[item_uid] = insert_index
                unique_items.append(item)
                insert_index += 1

        # If no new items are found, skip
        if not unique_items:
            return

        # Else if remote items, to make space for new unique items update the position of the existing items
        if remote:
            for item in self.data_items:
                old_item_uid = self.get_item_uid(item)
                if old_item_uid in self.item_uid_map:
                    new_items_map[old_item_uid] = insert_index + self.item_uid_map[old_item_uid]

        # Update the table model
        self.beginInsertRows(QModelIndex(), 0, len(unique_items) - 1)
        self.data_items = unique_items + self.data_items if remote else self.data_items + unique_items
        self.item_uid_map = new_items_map
        self.endInsertRows()


class TriblerContentModel(RemoteTableModel):
    column_headers = []
    column_width = {}
    column_flags = {}
    column_display_filters = {}

    def __init__(self, hide_xxx=False):
        RemoteTableModel.__init__(self, parent=None)
        self.data_items = []
        self.column_position = {name: i for i, name in enumerate(self.columns)}
        self.edit_enabled = False
        self.hide_xxx = hide_xxx

    def headerData(self, num, orientation, role=None):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.column_headers[num]

    def get_item_uid(self, item):
        item_uid = None
        if "infohash" in item:
            item_uid = item['infohash']
        elif "public_key" in item and "id" in item:
            item_uid = "%s:%s" % (item['public_key'], item['id'])
        return item_uid

    def rowCount(self, parent=QModelIndex()):
        return len(self.data_items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def flags(self, index):
        return self.column_flags[self.columns[index.column()]]

    def data(self, index, role):
        if role == Qt.DisplayRole or role == Qt.EditRole:
            column = self.columns[index.column()]
            data = self.data_items[index.row()][column] if column in self.data_items[index.row()] else u''
            return self.column_display_filters.get(column, str(data))(data) \
                if column in self.column_display_filters else data

    def reset(self):
        self.item_uid_map.clear()
        super(TriblerContentModel, self).reset()

    def update_torrent_info(self, update_dict):
        row = self.item_uid_map.get(update_dict["infohash"])
        if row:
            self.data_items[row].update(**update_dict)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.columns)), [])


class SearchResultsContentModel(TriblerContentModel):
    """
    Model for a list that shows search results.
    """
    columns = [u'category', u'name', u'torrents', u'size', u'updated', u'health', ACTION_BUTTONS]
    column_headers = [u'Category', u'Name', u'Torrents', u'Size', u'Updated', u'health', u'']
    column_flags = {
        u'category': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'name': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'torrents': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'size': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'updated': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'health': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        ACTION_BUTTONS: Qt.ItemIsEnabled | Qt.ItemIsSelectable
    }

    column_display_filters = {
        u'size': lambda data: (format_size(float(data)) if data != '' else ''),
        u'updated': pretty_date,
    }

    def __init__(self, **kwargs):
        TriblerContentModel.__init__(self, **kwargs)
        self.type_filter = ''


class ChannelsContentModel(TriblerContentModel):
    """
    This model represents a list of channels that can be displayed in a table view.
    """
    columns = [u'name', u'torrents', u'updated', u'subscribed']
    column_headers = [u'Channel name', u'Torrents', u'Updated', u'']
    column_flags = {
        u'name': Qt.ItemIsEnabled,
        u'torrents': Qt.ItemIsEnabled,
        u'updated': Qt.ItemIsEnabled,
        u'subscribed': Qt.ItemIsEnabled,
        ACTION_BUTTONS: Qt.ItemIsEnabled
    }

    column_display_filters = {
        u'updated': pretty_date,
    }

    def __init__(self, subscribed=False, **kwargs):
        TriblerContentModel.__init__(self, **kwargs)
        self.subscribed = subscribed


class TorrentsContentModel(TriblerContentModel):
    columns = [u'category', u'name', u'size', u'health', ACTION_BUTTONS]
    column_headers = [u'Category', u'Name', u'Size', u'Health', u'']
    column_flags = {
        u'category': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'name': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'size': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'health': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        ACTION_BUTTONS: Qt.ItemIsEnabled | Qt.ItemIsSelectable
    }

    column_display_filters = {
        u'size': lambda data: format_size(float(data)),
    }

    def __init__(self, channel_pk='', **kwargs):
        TriblerContentModel.__init__(self, **kwargs)
        self.channel_pk = channel_pk


class MyTorrentsContentModel(TorrentsContentModel):
    columns = [u'category', u'name', u'size', u'status', ACTION_BUTTONS]
    column_headers = [u'Category', u'Name', u'Size', u'', u'']
    column_flags = {
        u'category': Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable,
        u'name': Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable,
        u'size': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        u'status': Qt.ItemIsEnabled | Qt.ItemIsSelectable,
        ACTION_BUTTONS: Qt.ItemIsEnabled | Qt.ItemIsSelectable
    }

    row_edited = pyqtSignal(QModelIndex, str)

    def __init__(self, channel_pk='', **kwargs):
        TorrentsContentModel.__init__(self, channel_pk=channel_pk, **kwargs)
        self.exclude_deleted = False
        self.edit_enabled = True

    def setData(self, index, new_value, role=None):
        if role == Qt.EditRole:
            self.row_edited.emit(index, new_value)
            # TODO: reload the whole row from DB instead of just changing the displayed value
            self.data_items[index.row()][self.columns[index.column()]] = new_value
        return True
