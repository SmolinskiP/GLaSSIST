"""Room editor embedded in the existing Flet settings window."""
import asyncio
import json
import uuid

import flet as ft

from multi_room import configured_room_entries, rooms_enabled, validate_rooms


class RoomSettings:
    def __init__(self, page):
        self.page = page
        self.rows = []
        self.inputs = []
        self.outputs = []
        self.load_error = None
        self.enabled = ft.Switch(label='Use multiple rooms', value=rooms_enabled())
        self.cards = ft.Column(spacing=12)
        self.message = ft.Text()
        try:
            entries = configured_room_entries()
            if not isinstance(entries, list):
                raise ValueError('Saved rooms must be a list')
            if entries:
                validate_rooms(entries)
            for entry in entries:
                self.add_room(entry, update=False)
        except (ValueError, OSError, TypeError) as exc:
            self.load_error = str(exc)
            self.message.value = f'Cannot load saved rooms: {exc}. Reset the list to replace it.'
        self.content = ft.Container(padding=20, content=ft.Column([
            ft.Text('Rooms', size=24, weight=ft.FontWeight.BOLD),
            self.enabled,
            ft.Text('Assign a microphone and speaker to each room. One conversation runs at a time. '
                    'The voice hotkey uses the first room. Changes apply after restarting GLaSSIST.'),
            ft.Text('Enabling rooms selects ESPHome mode and enables local wake word detection. '
                    'Choose your wake word in the Wake Word tab.'),
            ft.Text('After restarting, add each GLaSSIST room device in Home Assistant. '
                    'Assign its area and preferred voice assistant there.'),
            ft.Text('This first version does not support room timers or announcements from Home Assistant.'),
            ft.Row([
                ft.ElevatedButton('Add room', icon=ft.Icons.ADD, on_click=lambda e: self.add_room()),
                ft.TextButton('Refresh devices', icon=ft.Icons.REFRESH, on_click=self.refresh_devices),
                ft.TextButton('Reset room list', on_click=self.reset),
            ], wrap=True),
            self.message, self.cards,
        ], scroll=ft.ScrollMode.AUTO))

    def _options(self, devices, selected):
        options = [ft.dropdown.Option(key=str(d['index']), text=f"{d['name']} ({d['index']})") for d in devices]
        if selected is not None and str(selected) not in {o.key for o in options}:
            options.append(ft.dropdown.Option(key=str(selected), text=f'Unavailable device ({selected})'))
        return options

    def add_room(self, entry=None, update=True):
        if entry is None:
            used = {r['port'].value for r in self.rows}
            port = 6053
            while str(port) in used:
                port += 1
            entry = {'id': 'room-' + uuid.uuid4().hex[:12], 'name': '', 'port': port,
                     'input_device': None, 'output_device': None}
        row = {'id': entry['id'],
               'name': ft.TextField(label='Room name', value=entry['name']),
               'input_device': ft.Dropdown(label='Microphone', value=None if entry['input_device'] is None else str(entry['input_device']), expand=True),
               'output_device': ft.Dropdown(label='Speaker', value=None if entry['output_device'] is None else str(entry['output_device']), expand=True),
               'port': ft.TextField(label='Connection port', value=str(entry['port']), width=180)}
        for key, devices in [('input_device', self.inputs), ('output_device', self.outputs)]:
            row[key].options = self._options(devices, row[key].value)
        card = ft.Container(padding=16, border=ft.border.all(1, ft.Colors.GREY_400), border_radius=8,
            content=ft.Column([
                row['name'], ft.Row([row['input_device'], row['output_device']]),
                ft.ExpansionTile(title=ft.Text('Advanced'), controls=[row['port'],
                    ft.Text(f"Home Assistant device: GLaSSIST-{row['id']}")]),
                ft.Row([ft.TextButton('Use for hotkey', on_click=lambda e: self.move_first(row)),
                        ft.TextButton('Remove room', on_click=lambda e: self.remove(row))]),
            ]))
        row['card'] = card
        self.rows.append(row)
        self.cards.controls.append(card)
        if update:
            self.page.update()

    def remove(self, row):
        self.rows.remove(row)
        self.cards.controls.remove(row['card'])
        self.page.update()

    def move_first(self, row):
        self.rows.remove(row)
        self.rows.insert(0, row)
        self.cards.controls = [r['card'] for r in self.rows]
        self.page.update()

    def reset(self, event=None):
        self.rows.clear()
        self.cards.controls.clear()
        self.load_error = None
        self.message.value = 'Room list cleared. Changes are saved only with Save Settings.'
        self.page.update()

    async def refresh_devices(self, event=None):
        def enumerate_devices():
            import pyaudio
            import utils
            audio = pyaudio.PyAudio()
            try:
                inputs = []
                for index in range(audio.get_device_count()):
                    info = audio.get_device_info_by_index(index)
                    if info.get('maxInputChannels', 0) > 0:
                        inputs.append({'index': index, 'name': utils.normalize_audio_device_name(info['name'])})
                return inputs, utils.get_available_output_devices()
            finally:
                audio.terminate()
        try:
            self.inputs, self.outputs = await asyncio.to_thread(enumerate_devices)
            for row in self.rows:
                for key, devices in [('input_device', self.inputs), ('output_device', self.outputs)]:
                    field = row[key]
                    field.options = self._options(devices, field.value)
            if not self.load_error:
                self.message.value = f'{len(self.inputs)} microphones and {len(self.outputs)} speakers found.'
        except Exception as exc:
            self.message.value = f'Cannot list audio devices: {exc}'
        if event is not None:
            self.page.update()

    def settings(self, animation_port=None):
        if self.load_error:
            raise ValueError('Saved rooms could not be loaded. Reset the room list before saving.')
        entries = []
        for number, row in enumerate(self.rows, 1):
            try:
                entries.append({'id': row['id'], 'name': row['name'].value.strip(),
                                'input_device': int(row['input_device'].value),
                                'output_device': int(row['output_device'].value), 'port': int(row['port'].value)})
            except (TypeError, ValueError):
                raise ValueError(f'Room {number}: select a microphone and speaker and enter a valid port.') from None
        if entries or self.enabled.value:
            validate_rooms(entries)
        if self.enabled.value and animation_port is not None and any(r['port'] == animation_port for r in entries):
            raise ValueError('A room connection port cannot be the same as the animation port.')
        return {'HA_ROOMS_ENABLED': 'true' if self.enabled.value else 'false',
                'HA_ROOMS': json.dumps(entries, ensure_ascii=False, separators=(',', ':'))}
