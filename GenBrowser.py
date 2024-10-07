import sys
import re
import threading
import json
import requests 
from bs4 import BeautifulSoup  
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit,
    QTabWidget, QTextEdit, QPushButton, QAction, QTabBar, QStylePainter,
    QStyleOptionTab, QStyle, QToolBar, QLabel, QDialog, QListWidget,
    QListWidgetItem, QMessageBox, QComboBox, QInputDialog, QProgressBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QRect, QSize, pyqtSlot, QUrl, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtGui import QIcon
import ollama

# ------------------ Configuration ------------------

# Initialize the Ollama client with the correct server address
OLLAMA_SERVER = "http://localhost:11434"

# Wikimedia Commons API configuration
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"

# ---------------------------------------------------

# Initialize the Ollama client
try:
    ollama_client = ollama.Client(host=OLLAMA_SERVER, timeout=600)  # Increased timeout to 10 minutes
except Exception as e:
    print(f"Failed to connect to Ollama server: {e}")
    sys.exit(1)


class WebBridge(QObject):
    """Bridge between Python and JavaScript."""
    request_edit = pyqtSignal(str)  

    @pyqtSlot(str)
    def send_to_python(self, message):
        """Receive messages from JavaScript."""
        self.request_edit.emit(message)


class ChatDialog(QDialog):
    """Chat window for interacting with the AI assistant."""
    def __init__(self, parent=None, topic="", web_view=None):
        super().__init__(parent)
        self.setWindowTitle("AI Assistant Chat")
        self.setGeometry(150, 150, 400, 500)
        self.topic = topic
        self.web_view = web_view

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.layout.addWidget(self.chat_display)

        self.input_bar = QLineEdit()
        self.input_bar.setPlaceholderText("Type your message here...")
        self.input_bar.returnPressed.connect(self.send_message)
        self.layout.addWidget(self.input_bar)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        self.layout.addWidget(self.send_button)

    def append_message(self, sender, message):
        """Append a message to the chat display."""
        self.chat_display.append(f"<b>{sender}:</b> {message}")

    def send_message(self):
        """Handle sending a message."""
        user_message = self.input_bar.text().strip()
        if not user_message:
            return
        self.append_message("You", user_message)
        self.input_bar.clear()
        self.process_message(user_message)

    def process_message(self, message):
        """Send the message to the AI and handle the response."""
        def generate_response():
            try:
                ai_prompt = f"You are a web assistant. Modify the following HTML/JavaScript based on the user's request:\n\n{message}"
                print("Sending chat request to Ollama client...")
                response = ollama_client.chat(
                    model=self.parent().current_model,
                    messages=[
                        {"role": "system", "content": "You are an assistant that helps edit HTML and JavaScript code."},
                        {"role": "user", "content": ai_prompt}
                    ]
                )
                print("Received response from Ollama client.")

                if response and 'message' in response and 'content' in response['message']:
                    ai_response = response['message']['content']
                    # Assume the AI returns the modified HTML/JavaScript
                    self.append_message("AI Assistant", ai_response)
                    # Send the response back to the web page to apply changes
                    self.web_view.page().runJavaScript(f"applyAIChanges(`{ai_response}`);")
                else:
                    self.append_message("AI Assistant", "Sorry, I couldn't generate a response.")
            except Exception as e:
                self.append_message("AI Assistant", f"Error: {str(e)}")
                print(f"Error during AI response generation: {e}")

        threading.Thread(target=generate_response, daemon=True).start()


class ShowCodeDialog(QDialog):
    """Dialog to show and edit the page's HTML/CSS/JS."""
    def __init__(self, parent=None, html_content="", web_view=None):
        super().__init__(parent)
        self.setWindowTitle("Show Code")
        self.setGeometry(200, 200, 600, 600)
        self.web_view = web_view

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.code_display = QTextEdit()
        self.code_display.setPlainText(html_content)
        self.layout.addWidget(self.code_display)

        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.save_changes)
        self.layout.addWidget(self.save_button)

    def save_changes(self):
        """Apply the edited code back to the web view."""
        edited_html = self.code_display.toPlainText()
        self.web_view.setHtml(edited_html)
        self.close()


class BookmarksDialog(QDialog):
    """Dialog to manage bookmarks."""
    def __init__(self, parent=None, bookmarks=None):
        super().__init__(parent)
        self.setWindowTitle("Bookmarks")
        self.setGeometry(250, 250, 400, 400)
        self.bookmarks = bookmarks if bookmarks else {}

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.list_widget = QListWidget()
        self.populate_bookmarks()
        self.layout.addWidget(self.list_widget)

        self.load_button = QPushButton("Load Bookmark")
        self.load_button.clicked.connect(self.load_bookmark)
        self.layout.addWidget(self.load_button)

        self.delete_button = QPushButton("Delete Bookmark")
        self.delete_button.clicked.connect(self.delete_bookmark)
        self.layout.addWidget(self.delete_button)

    def populate_bookmarks(self):
        """Populate the list widget with bookmarks."""
        self.list_widget.clear()
        for title, url in self.bookmarks.items():
            item = QListWidgetItem(f"{title} - {url}")
            self.list_widget.addItem(item)

    def load_bookmark(self):
        """Load the selected bookmark."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a bookmark to load.")
            return
        item_text = selected_items[0].text()
        title, url = item_text.split(" - ", 1)
        self.parent().navigate_to_url(url)
        self.close()

    def delete_bookmark(self):
        """Delete the selected bookmark."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a bookmark to delete.")
            return
        item_text = selected_items[0].text()
        title, url = item_text.split(" - ", 1)
        reply = QMessageBox.question(
            self, 'Confirm Deletion',
            f"Are you sure you want to delete the bookmark '{title}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self.bookmarks[title]
            self.populate_bookmarks()
            QMessageBox.information(self, "Deleted", f"Bookmark '{title}' has been deleted.")
            self.parent().save_bookmarks()  


class CustomWebEnginePage(QWebEnginePage):
    """Custom QWebEnginePage to intercept navigation requests."""
    def __init__(self, parent=None, browser=None, base_topic="", base_design=""):
        super().__init__(parent)
        self.browser = browser
        self.base_topic = base_topic
        self.base_design = base_design

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        if _type == QWebEnginePage.NavigationTypeLinkClicked:
            url_str = url.toString()
            # Determine if the link is internal or external
            if url_str.startswith("http") or url_str.startswith("www"):
                # External link
                self.browser.generate_new_tab_from_link(url_str)
            else:
                # Internal link
                link_text = url.toString()
                self.browser.generate_internal_page(self.base_topic, link_text, self.base_design)
            return False  
        return super().acceptNavigationRequest(url, _type, isMainFrame)


class SignalCommunicator(QObject):
    """A helper class to define custom signals."""
    html_ready_signal = pyqtSignal(str, str)  


class ClosableTabBar(QTabBar):
    """Custom QTabBar that adds a close button to each tab."""
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        size.setWidth(size.width() + 25)  
        return size

    def paintEvent(self, event):
        """Custom paint event to draw close buttons."""
        painter = QStylePainter(self)
        option = QStyleOptionTab()

        for index in range(self.count()):
            self.initStyleOption(option, index)
            painter.drawControl(QStyle.CE_TabBarTab, option)

            # Draw the close button closer to the text
            rect = self.tabRect(index)
            icon = self.style().standardIcon(QStyle.SP_TitleBarCloseButton)
            # Adjust the close button position vertically centered
            close_rect = QRect(rect.right() - 20, rect.top() + (rect.height() - 16) // 2, 16, 16)
            icon.paint(painter, close_rect)

    def mousePressEvent(self, event):
        """Handles mouse press events to detect close button clicks."""
        # Check if the close button is clicked
        for index in range(self.count()):
            rect = self.tabRect(index)
            close_rect = QRect(rect.right() - 20, rect.top() + (rect.height() - 16) // 2, 16, 16)
            if close_rect.contains(event.pos()):
                self.parent().removeTab(index)  
                return
        super().mousePressEvent(event)


class GenerativeBrowser(QMainWindow):
    """Main browser window."""
    content_generated = pyqtSignal(str, str)  

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gen Browser Prototype")
        self.setGeometry(100, 100, 1280, 720)

        # Remove window frame to create a frameless window
        self.setWindowFlags(Qt.FramelessWindowHint)

        # Dark mode state
        self.dark_mode = True

        # Bookmarks storage
        self.bookmarks = {}
        self.load_bookmarks()  

        # Current model
        self.available_models = {
            "qwen2.5": ["qwen2.5", "qwen2.5:14b", "qwen2.5:3b", "qwen2.5:32b"],
            "llama3.2": ["llama3.2", "llama3.2:1b"],
            "llama3.1": ["llama3.1:70b"],
            "gemma2": ["gemma2:27b"],
            "phi3.5": ["phi3.5"],
            "codegemma": ["codegemma"]
        }
        self.current_model = "qwen2.5"

        # Create main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Create custom title bar
        self.create_title_bar()

        # Create a horizontal layout for the address bar and send button
        self.top_bar_layout = QHBoxLayout()
        self.top_bar_layout.setContentsMargins(10, 10, 10, 10)
        self.top_bar_layout.setSpacing(10)

        # Address bar
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Enter your query or URL (e.g., thing i need.gen)...")
        self.address_bar.setFixedHeight(30)
        self.address_bar.returnPressed.connect(self.generate_content)
        self.top_bar_layout.addWidget(self.address_bar)

        # Add 'Send' button next to the address bar
        self.send_button = QPushButton("Send")
        self.send_button.setFixedHeight(30)
        self.send_button.setFixedWidth(100)
        self.send_button.clicked.connect(self.generate_content)
        self.top_bar_layout.addWidget(self.send_button)

        self.main_layout.addLayout(self.top_bar_layout)

        # Create a navigation toolbar
        self.navigation_toolbar = QToolBar("Navigation")
        self.navigation_toolbar.setIconSize(QSize(16, 16))
        self.navigation_toolbar.setStyleSheet("background-color: #555555;")
        self.main_layout.addWidget(self.navigation_toolbar)

        # Add navigation buttons with simple text-based icons
        self.add_navigation_buttons()

        # Add model selection dropdown
        self.model_combo = QComboBox()
        for model, sizes in self.available_models.items():
            self.model_combo.addItem(model)
            for size in sizes:
                self.model_combo.addItem(f"  {size}")
        self.model_combo.setCurrentText(self.current_model)
        self.model_combo.currentTextChanged.connect(self.change_model)
        self.navigation_toolbar.addWidget(self.model_combo)

        # Add bookmarks button
        self.bookmarks_button = QAction("🔖", self)  
        self.bookmarks_button.setToolTip("Bookmarks")
        self.bookmarks_button.triggered.connect(self.open_bookmarks)
        self.navigation_toolbar.addAction(self.bookmarks_button)

        # Add 'Add Bookmark' button
        self.add_bookmark_button = QAction("⭐", self)  
        self.add_bookmark_button.setToolTip("Add Bookmark")
        self.add_bookmark_button.triggered.connect(self.add_bookmark)
        self.navigation_toolbar.addAction(self.add_bookmark_button)

        # Tabs for generated content with custom closable tab bar
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabBar(ClosableTabBar(self.tab_widget))  
        self.main_layout.addWidget(self.tab_widget)

        # Create a default chat-like tab
        self.create_chat_tab()

        # Set default theme to dark mode *after* initializing components
        self.set_dark_mode(self.dark_mode)

        # Connect content generated signal to content updater
        self.content_generated.connect(self.update_tab_content)

        # Create an instance of SignalCommunicator
        self.signal_communicator = SignalCommunicator()

        # Connect custom signal to a slot function for real-time updates
        self.signal_communicator.html_ready_signal.connect(self.set_html_in_tab)

        # Store base designs for sites
        self.site_designs = {}  

        # Initialize progress bar
        self.progress_dialog = None

    def update_tab_content(self, title, content):
        """Update the content of the currently active tab."""
        for index in range(self.tab_widget.count()):
            if self.tab_widget.tabText(index) == title:
                widget = self.tab_widget.widget(index)
                if isinstance(widget, QWebEngineView):
                    widget.setHtml(content)
                    break

    def create_title_bar(self):
        """Creates a custom title bar with window controls."""
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(40)
        self.title_bar.setStyleSheet("background-color: #444444;")
        self.title_bar_layout = QHBoxLayout(self.title_bar)
        self.title_bar_layout.setContentsMargins(10, 0, 10, 0)
        self.title_bar_layout.setSpacing(0)

        # Title label
        self.title_label = QLabel("Gen Browser Prototype")
        self.title_label.setStyleSheet("color: white; font-size: 14px;")
        self.title_bar_layout.addWidget(self.title_label)

        self.title_bar_layout.addStretch()

        # Minimize button
        self.minimize_button = QPushButton("_")
        self.minimize_button.setFixedSize(30, 30)
        self.minimize_button.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.title_bar_layout.addWidget(self.minimize_button)

        # Close button
        self.close_button = QPushButton("X")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #FF5C5C;
            }
        """)
        self.close_button.clicked.connect(self.close)
        self.title_bar_layout.addWidget(self.close_button)

        self.main_layout.addWidget(self.title_bar)

        # Implement window dragging
        self.old_pos = self.pos()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.y() <= self.title_bar.height():
                self.dragging = True
                self.offset = event.globalPos() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, 'dragging') and self.dragging:
            self.move(event.globalPos() - self.offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dragging = False
        super().mouseReleaseEvent(event)

    def add_navigation_buttons(self):
        """Adds navigation buttons with simple text-based icons."""
        # Back button
        self.back_button = QAction("<", self)
        self.back_button.setToolTip("Back")
        self.back_button.triggered.connect(self.navigate_back)
        self.navigation_toolbar.addAction(self.back_button)

        # Forward button
        self.forward_button = QAction(">", self)
        self.forward_button.setToolTip("Forward")
        self.forward_button.triggered.connect(self.navigate_forward)
        self.navigation_toolbar.addAction(self.forward_button)

        # Reroll button
        self.reroll_button = QAction("🔄", self)  
        self.reroll_button.setToolTip("Reroll Website")
        self.reroll_button.triggered.connect(self.reroll_page)
        self.navigation_toolbar.addAction(self.reroll_button)

        # AI Assistant Button
        self.assistant_button = QAction("🤖", self)  
        self.assistant_button.setToolTip("Chat with AI Assistant")
        self.assistant_button.triggered.connect(self.open_assistant_chat)
        self.navigation_toolbar.addAction(self.assistant_button)

        # Show Code Button
        self.show_code_button = QAction("🔍", self)  
        self.show_code_button.setToolTip("Show Code")
        self.show_code_button.triggered.connect(self.show_code)
        self.navigation_toolbar.addAction(self.show_code_button)

        # Home button
        self.home_button = QAction("🏠", self)
        self.home_button.setToolTip("Home")
        self.home_button.triggered.connect(self.navigate_home)
        self.navigation_toolbar.addAction(self.home_button)

        # Dark/Light mode toggle
        self.theme_toggle = QAction("🌙", self)
        self.theme_toggle.setToolTip("Toggle Dark/Light Mode")
        self.theme_toggle.setCheckable(True)
        self.theme_toggle.triggered.connect(self.toggle_dark_light_mode)
        self.navigation_toolbar.addAction(self.theme_toggle)

        # Fullscreen toggle button
        self.fullscreen_button = QAction("⛶", self)  
        self.fullscreen_button.setToolTip("Toggle Full Screen")
        self.fullscreen_button.triggered.connect(self.toggle_fullscreen)
        self.navigation_toolbar.addAction(self.fullscreen_button)

    def change_model(self, model_text):
        """Change the current AI model based on user selection."""
        model_text = model_text.strip()
        if model_text in self.available_models:
            # Select the default size for the model
            self.current_model = self.available_models[model_text][0]
            self.model_combo.setCurrentText(self.current_model)
        else:
            # User selected a specific size
            self.current_model = model_text

    def open_bookmarks(self):
        """Open the bookmarks management dialog."""
        dialog = BookmarksDialog(self, self.bookmarks)
        dialog.exec_()

    def open_assistant_chat(self):
        """Open the AI assistant chat dialog for the current tab."""
        current_tab = self.tab_widget.currentWidget()
        current_title = self.tab_widget.tabText(self.tab_widget.currentIndex())
        if current_title.startswith("Building "):
            # Extract the original query
            query = current_title.replace("Building ", "")
            topic = query.replace(".gen", "").strip()
            if not topic:
                self.chat_display.append("Gen Browser: Invalid topic for assistant chat.")
                return
            # Open the chat dialog
            chat_dialog = ChatDialog(self, topic=topic, web_view=current_tab)
            chat_dialog.exec_()
        else:
            QMessageBox.information(self, "Assistant Chat", "Assistant chat is only available for generated websites.")

    def show_code(self):
        """Show the current page's code."""
        current_tab = self.tab_widget.currentWidget()
        if isinstance(current_tab, QWebEngineView):
            def get_html(html):
                """Callback to receive HTML content."""
                code_dialog = ShowCodeDialog(self, html_content=html, web_view=current_tab)
                code_dialog.exec_()

            current_tab.page().toHtml(get_html)
        else:
            QMessageBox.information(self, "Show Code", "No web page available to show code.")

    def create_chat_tab(self):
        """Creates the default chat-like tab."""
        # Create a new tab resembling a chat interface
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Welcome to the Gen Browser! Enter your query above to get started...")

        chat_layout.addWidget(self.chat_display)
        chat_layout.setContentsMargins(10, 10, 10, 10)

        tab_index = self.tab_widget.addTab(chat_tab, "Main Chat")
        self.tab_widget.setCurrentIndex(tab_index)

    def create_new_tab(self, title, is_loading=True, base_topic="", base_design=""):
        """Creates a new tab with a QWebEngineView."""
        new_tab = QWebEngineView()
        new_page = CustomWebEnginePage(browser=self, base_topic=base_topic, base_design=base_design)
        new_tab.setPage(new_page)
        if is_loading:
            # Display a dynamic loading message with rotating text and assistant button
            loading_html = """
            <html>
                <head>
                    <title>Loading...</title>
                    <style>
                        body {
                            display: flex;
                            flex-direction: column;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            font-family: Arial, sans-serif;
                            background-color: #333;
                            color: #fff;
                            position: relative;
                        }
                        .loader {
                            border: 8px solid #f3f3f3;
                            border-top: 8px solid #3498db;
                            border-radius: 50%;
                            width: 60px;
                            height: 60px;
                            animation: spin 2s linear infinite;
                        }
                        @keyframes spin {
                            0% { transform: rotate(0deg); }
                            100% { transform: rotate(360deg); }
                        }
                        .message {
                            margin-top: 20px;
                            font-size: 1.2em;
                            font-style: italic;
                            height: 1.5em;
                            text-align: center;
                        }
                        .assistant-button {
                            position: absolute;
                            bottom: 20px;
                            right: 20px;
                            background-color: #3498db;
                            color: white;
                            border: none;
                            border-radius: 50%;
                            width: 50px;
                            height: 50px;
                            font-size: 24px;
                            cursor: pointer;
                        }
                        .assistant-button:hover {
                            background-color: #2980b9;
                        }
                    </style>
                    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
                    <script>
                        var bridge = null;
                        new QWebChannel(qt.webChannelTransport, function(channel) {
                            bridge = channel.objects.bridge;
                        });

                        function applyAIChanges(changes) {
                            document.body.innerHTML = changes;
                        }
                    </script>
                </head>
                <body>
                    <div class="loader"></div>
                    <div class="message" id="message">Generating your site...</div>

                    <button class="assistant-button" onclick="bridge.send_to_python('Open Assistant')">🤖</button>

                    <script>
                        const messages = [
                            "Generating your site...",
                            "There are no ads on the Gen Web...",
                            "Thinking about the topic...",
                            "Gen Web...There's a young Spiderman joke there somewhere...",
                            "Fetching relevant images...",
                            "The future is now!",
                            "What an interesting topic...",
                            "Almost there..."
                        ];
                        let index = 0;
                        setInterval(() => {
                            index = (index + 1) % messages.length;
                            document.getElementById('message').innerText = messages[index];
                        }, 2000);
                    </script>
                </body>
            </html>
            """
            new_tab.setHtml(loading_html)

            # Set up WebChannel for communication
            channel = QWebChannel()
            bridge = WebBridge()
            channel.registerObject('bridge', bridge)
            new_tab.page().setWebChannel(channel)

            # Connect the bridge signal to open the assistant chat
            bridge.request_edit.connect(lambda msg, tab=new_tab: self.handle_webpage_request(msg, tab))

            # Start generating content after the loading screen is set
            QTimer.singleShot(0, lambda: self.generate_html_for_gen_site(base_topic, f"{base_topic}.gen", title, base_design))
        else:
            # For non-loading tabs, set default content or handle differently
            new_tab.setHtml("<html><body><h1>New Tab</h1></body></html>")

        tab_index = self.tab_widget.addTab(new_tab, title)
        self.tab_widget.setCurrentIndex(tab_index)
        return new_tab

    def handle_webpage_request(self, message, tab):
        """Handle requests from the web page."""
        if message == "Open Assistant":
            # Open the assistant chat for this tab
            tab_title = self.tab_widget.tabText(self.tab_widget.indexOf(tab))
            if tab_title.startswith("Building "):
                # Extract the original query
                query = tab_title.replace("Building ", "")
                topic = query.replace(".gen", "").strip()
                if not topic:
                    self.chat_display.append("Gen Browser: Invalid topic for assistant chat.")
                    return
                # Open the chat dialog
                chat_dialog = ChatDialog(self, topic=topic, web_view=tab)
                chat_dialog.exec_()
            else:
                QMessageBox.information(self, "Assistant Chat", "Assistant chat is only available for generated websites.")

    def set_html_in_tab(self, title, html_content):
        """Sets the HTML content in the specified tab."""
        # Fetch images based on the topic
        topic_match = re.match(r"Building\s+(.*)", title)
        if topic_match:
            topic = topic_match.group(1).replace(".gen", "").strip()
        else:
            topic = "default"

        # Parse the HTML and replace image placeholders with actual URLs
        soup = BeautifulSoup(html_content, 'html.parser')
        img_tags = soup.find_all('img')

        # List to keep track of threads
        threads = []

        def fetch_and_set_image(img_tag, retries=3):
            # Simplify the query to improve image search results
            if 'alt' in img_tag.attrs and img_tag['alt']:
                query = img_tag['alt']
                # Simplify query by removing special characters and taking first few words
                query = re.sub(r'[^\w\s]', '', query)
                query = ' '.join(query.split()[:5])
            else:
                query = topic
            image_url = self.fetch_image_with_retries(query, retries)
            print(f"Setting image for '{query}': {image_url}")
            img_tag['src'] = image_url

            # Add class for responsive images
            if 'class' in img_tag.attrs:
                img_tag['class'].append('responsive-img')
            else:
                img_tag['class'] = ['responsive-img']

        def fetch_and_set_background_image(element, retries=3):
            style = element.get('style', '')
            if 'background-image' in style:
                # Extract the URL inside background-image: url(...)
                match = re.search(r'background-image\s*:\s*url\([\'"]?(.*?)[\'"]?\)', style)
                if match:
                    bg_url = match.group(1)
                    # If the URL is a placeholder, fetch a new image
                    if 'path/to/your/background.jpg' in bg_url or 'placeholder' in bg_url or 'your_image_here' in bg_url:
                        # Use the alt attribute or topic as the query
                        query = element.get('alt', topic)
                        query = re.sub(r'[^\w\s]', '', query)
                        query = ' '.join(query.split()[:5])
                        image_url = self.fetch_image_with_retries(query, retries)
                        print(f"Setting background image for '{query}': {image_url}")
                        # Replace the URL in the style
                        new_style = style.replace(bg_url, image_url)
                        element['style'] = new_style

        # Fetch images in threads to prevent blocking
        for img in img_tags:
            thread = threading.Thread(target=fetch_and_set_image, args=(img,))
            threads.append(thread)
            thread.start()

        # Process inline styles with background-image
        for element in soup.find_all(style=True):
            thread = threading.Thread(target=fetch_and_set_background_image, args=(element,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

        # Inject CSS styles for responsive images and containers
        style_tag = soup.new_tag('style')
        style_tag.string = """
        img.responsive-img {
            max-width: 100%;
            height: auto;
            display: block;
        }
        .container, .content-container, .content-section {
            width: 100%;
            overflow: hidden;
        }
        """
        # Include external CSS libraries
        bootstrap_css = soup.new_tag('link', rel='stylesheet', href='https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css')
        # Include external JS libraries
        bootstrap_js = soup.new_tag('script', src='https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js')

        jquery_js = soup.new_tag('script', src='https://code.jquery.com/jquery-3.5.1.slim.min.js')

        popper_js = soup.new_tag('script', src='https://cdn.jsdelivr.net/npm/popper.js@1.16.1/dist/umd/popper.min.js')

        if soup.head:
            soup.head.append(style_tag)
            soup.head.append(bootstrap_css)
        else:
            # If there's no <head>, create one
            head_tag = soup.new_tag('head')
            head_tag.append(style_tag)
            head_tag.append(bootstrap_css)
            soup.insert(0, head_tag)

        # Append scripts before closing body tag
        if soup.body:
            soup.body.append(jquery_js)
            soup.body.append(popper_js)
            soup.body.append(bootstrap_js)
        else:
            # If there's no <body>, create one
            body_tag = soup.new_tag('body')
            body_tag.append(jquery_js)
            body_tag.append(popper_js)
            body_tag.append(bootstrap_js)
            soup.insert(len(soup.contents), body_tag)

        final_html = str(soup)

        # Set the modified HTML to the tab
        for index in range(self.tab_widget.count()):
            if self.tab_widget.tabText(index) == title:
                widget = self.tab_widget.widget(index)
                if isinstance(widget, QWebEngineView):
                    widget.setHtml(final_html)
                    # Store the base design if it's the main page
                    if title.startswith("Building "):
                        base_topic = topic
                        self.site_designs[base_topic] = final_html
                break

    def fetch_image_with_retries(self, query, retries=3):
        """Fetch a single image URL from Wikimedia Commons based on the query with retries."""
        for attempt in range(retries):
            image_url = self.fetch_image(query)
            if image_url and not image_url.startswith("https://via.placeholder.com"):
                return image_url
            # Modify the query slightly for the next attempt
            query += " photo"
        # After retries, return the placeholder
        return "https://via.placeholder.com/300x200.png?text=No+Image"

    def fetch_image(self, query):
        """Fetch a single image URL from Wikimedia Commons based on the query."""
        url = WIKIMEDIA_API_URL
        # First, search for images in the file namespace
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,  
            "srlimit": 20  
        }
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')
        try:
            response = requests.get(url, params=search_params)
            if response.status_code == 200:
                data = response.json()
                if "query" in data and "search" in data["query"]:
                    search_results = data["query"]["search"]
                    for result in search_results:
                        title = result['title']
                        # Now get imageinfo for this title
                        imageinfo_params = {
                            "action": "query",
                            "format": "json",
                            "titles": title,
                            "prop": "imageinfo",
                            "iiprop": "url|mime",
                            "iiurlwidth": 800,
                            "iiurlheight": 600
                        }
                        imageinfo_response = requests.get(url, params=imageinfo_params)
                        if imageinfo_response.status_code == 200:
                            imageinfo_data = imageinfo_response.json()
                            if "query" in imageinfo_data and "pages" in imageinfo_data["query"]:
                                page_data = next(iter(imageinfo_data["query"]["pages"].values()))
                                if "imageinfo" in page_data:
                                    imageinfo = page_data["imageinfo"][0]
                                    mime_type = imageinfo.get("mime", "")
                                    image_url = imageinfo.get("url", "")
                                    if mime_type.startswith("image/") and image_url.lower().endswith(valid_extensions):
                                        return image_url
                    # If no image found, use a default placeholder
                    print(f"No images found for query: {query}")
                    return "https://via.placeholder.com/300x200.png?text=No+Image"
                else:
                    print(f"No search results for query: {query}")
                    return "https://via.placeholder.com/300x200.png?text=No+Image"
            else:
                print(f"Failed to fetch image from Wikimedia Commons: {response.status_code}")
                return "https://via.placeholder.com/300x200.png?text=No+Image"
        except Exception as e:
            print(f"Exception while fetching image: {e}")
            return "https://via.placeholder.com/300x200.png?text=No+Image"

    def load_bookmarks(self):
        """Load bookmarks from a JSON file."""
        try:
            with open("bookmarks.json", "r") as file:
                self.bookmarks = json.load(file)
        except FileNotFoundError:
            self.bookmarks = {}
        except json.JSONDecodeError:
            self.bookmarks = {}

    def save_bookmarks(self):
        """Save bookmarks to a JSON file."""
        try:
            with open("bookmarks.json", "w") as file:
                json.dump(self.bookmarks, file, indent=4)
        except Exception as e:
            print(f"Failed to save bookmarks: {e}")

    def add_bookmark(self):
        """Add the current page to bookmarks."""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            QMessageBox.warning(self, "No Page", "There is no page to bookmark.")
            return
        current_title = self.tab_widget.tabText(current_index)
        current_tab = self.tab_widget.widget(current_index)
        if isinstance(current_tab, QWebEngineView):
            url = current_tab.url().toString()
        else:
            url = ""
        if not url:
            # For generated pages without a URL, we can use the title
            url = current_title

        # Use a dialog to get a name for the bookmark
        bookmark_name, ok = QInputDialog.getText(self, "Add Bookmark", "Bookmark Name:", QLineEdit.Normal, current_title)
        if ok and bookmark_name:
            self.bookmarks[bookmark_name] = url
            self.save_bookmarks()
            QMessageBox.information(self, "Bookmark Added", f"Bookmark '{bookmark_name}' added.")

    def generate_internal_page(self, base_topic, link_text, base_design):
        """Generates a page for an internal link."""
        page_type = link_text.strip('/')
        new_topic = f"{base_topic} - {page_type}"
        tab_title = f"Building {new_topic}.gen"
        self.create_new_tab(tab_title, is_loading=True, base_topic=base_topic, base_design=base_design)
        self.generate_html_for_gen_site(new_topic, f"{new_topic}.gen", tab_title, base_design)

    def generate_new_tab_from_link(self, link_text):
        """Generates a new tab for an external link."""
        new_topic = link_text.strip('/')
        tab_title = f"Building {new_topic}.gen"
        self.create_new_tab(tab_title, is_loading=True, base_topic=new_topic)
        self.generate_html_for_gen_site(new_topic, f"{new_topic}.gen", tab_title)

    def pull_model(self, model_name):
        """Pull the model if it's not available locally."""
        self.show_progress_dialog(f"Pulling model '{model_name}'...")
        try:
            for progress in ollama_client.pull(model_name):
                # Update progress bar
                self.update_progress_dialog(progress.get('progress', 0))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to pull model '{model_name}': {str(e)}")
            print(f"Failed to pull model '{model_name}': {e}")
        finally:
            self.hide_progress_dialog()

    def show_progress_dialog(self, message):
        """Display a progress dialog."""
        self.progress_dialog = QDialog(self)
        self.progress_dialog.setWindowTitle("Please Wait")
        self.progress_dialog.setFixedSize(300, 100)
        layout = QVBoxLayout()
        label = QLabel(message)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        layout.addWidget(label)
        layout.addWidget(self.progress_bar)
        self.progress_dialog.setLayout(layout)
        self.progress_dialog.show()

    def update_progress_dialog(self, progress):
        """Update the progress bar."""
        self.progress_bar.setValue(int(progress * 100))

    def hide_progress_dialog(self):
        """Hide the progress dialog."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

    def generate_content(self):
        """Generates content based on the user's query."""
        query = self.address_bar.text()
        if query.endswith(".gen"):
            # Handle .gen requests as website creation based on topic
            topic = query.replace(".gen", "").strip()
            if not topic:
                self.chat_display.append("Gen Browser: Please provide a valid topic before '.gen'.")
                return
            tab_title = f"Building {query}"
            self.create_new_tab(tab_title, is_loading=True, base_topic=topic)
        else:
            # Generate HTML content based on the natural language query
            self.generate_html_from_query(query)

        self.chat_display.append(f"User: {query}")
        self.chat_display.append(f"Gen Browser: Generating content for '{query}'")
        self.address_bar.clear()

    def generate_html_for_gen_site(self, topic, query, tab_title, base_design=""):
        """Generates HTML content for a .gen request."""
        def generate():
            try:
                print("Starting content generation...")
                print(f"Sending request to model with topic: {topic}")

                # Updated AI prompt
                ai_prompt = f"""
                Using HTML, CSS, and JavaScript, create a unique, modern, and professional website about {topic}.
                Incorporate modern web design practices using frameworks like Bootstrap or Materialize.
                Be imaginative, incorporating design elements, interactive features, animations, and layouts.
                Ensure that all code is valid and tested, and avoid any JavaScript errors.
                Important: Do not use any placeholder text like "Lorem ipsum". Instead, write meaningful content related to {topic}.
                Include relevant images in the website by adding <img> tags with descriptive alt attributes, and include images using inline CSS styles like 'background-image', but use placeholder URLs like 'your_image_here.jpg'.
                Do not include any actual image URLs in the code.
                Do not include any external links except for CDN links to Bootstrap or other frameworks.
                """

                # If base_design is provided, instruct the AI to keep the same design
                if base_design:
                    ai_prompt += f"\n\nMaintain the same overall design and layout as the following HTML:\n\n{base_design}"

                try:
                    response = ollama_client.chat(
                        model=self.current_model,
                        messages=[
                            {"role": "system", "content": "You are an assistant that generates unique, creative, and high-quality HTML, CSS, and JavaScript content without any markdown or code blocks."},
                            {"role": "user", "content": ai_prompt}
                        ]
                    )
                    print("Received response from Ollama client.")
                except Exception as e:
                    print(f"Exception during Ollama chat: {e}")
                    if "model not found" in str(e).lower():
                        # Model not found, try pulling it
                        print(f"Model '{self.current_model}' not found. Attempting to pull the model.")
                        self.pull_model(self.current_model)
                        # Retry after pulling
                        response = ollama_client.chat(
                            model=self.current_model,
                            messages=[
                                {"role": "system", "content": "You are an assistant that generates unique, creative, and high-quality HTML, CSS, and JavaScript content without any markdown or code blocks."},
                                {"role": "user", "content": ai_prompt}
                            ]
                        )
                        print("Received response from Ollama client after pulling the model.")
                    else:
                        raise e

                print("Received response from model:", response)

                if response and 'message' in response and 'content' in response['message']:
                    content_stream = response['message']['content']
                    print("Content stream received from model.")

                    # Extract HTML from the content stream
                    generated_html = self.extract_html(content_stream)
                    print("Extracted HTML content.")

                    # Emit the signal to set the HTML in the tab
                    self.signal_communicator.html_ready_signal.emit(tab_title, generated_html)
                else:
                    print("No valid content received from model.")
                    error_html = f"""
                    <html>
                        <head><title>Error</title></head>
                        <body><h1>Error generating content</h1><p>No content was generated by the model.</p></body>
                    </html>
                    """
                    self.signal_communicator.html_ready_signal.emit(tab_title, error_html)

            except Exception as e:
                error_html = f"""
                <html>
                    <head><title>Error</title></head>
                    <body><h1>Error generating content</h1><p>{str(e)}</p></body>
                </html>
                """
                self.signal_communicator.html_ready_signal.emit(tab_title, error_html)
                print(f"Error generating content for {query}: {e}")

        # Start the HTML generation in a new thread to keep UI responsive
        threading.Thread(target=generate, daemon=True).start()

    def extract_html(self, content):
        """
        Extracts HTML content from the model's response.
        It first looks for HTML within ```html ... ``` code blocks.
        If not found, it searches for <html> tags.
        """
        # Attempt to extract HTML within ```html ... ``` code blocks
        code_block_match = re.search(r'```html\s*([\s\S]*?)\s*```', content, re.IGNORECASE)
        if code_block_match:
            return code_block_match.group(1)

        # Fallback: Extract content between <html> tags
        html_match = re.search(r'<html[\s\S]*?</html>', content, re.IGNORECASE)
        if html_match:
            return html_match.group(0)

        # If no HTML is found, return entire content
        print("HTML tags not found in content. Using entire content.")
        return content  

    def toggle_dark_light_mode(self):
        """Toggles between dark and light mode with corresponding icons."""
        self.dark_mode = not self.dark_mode
        self.set_dark_mode(self.dark_mode)
        if self.dark_mode:
            self.theme_toggle.setText("🌞")
        else:
            self.theme_toggle.setText("🌙")

    def set_dark_mode(self, enabled):
        """Applies the dark or light theme."""
        dark_palette = """
            QMainWindow, QWidget {
                background-color: #282828;
                color: #FFFFFF;
                border: none;
            }
            QLineEdit, QPushButton {
                background-color: #3B3B3B;
                color: #E0E0E0;
                border: 1px solid #555555;
            }
            QLineEdit:focus, QPushButton:focus {
                border: 1px solid #777777;
            }
            QMenuBar, QMenu {
                background-color: #282828;
                color: #FFFFFF;
            }
            QMenu::item:selected {
                background-color: #444444;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #2E2E2E;
            }
            QTabBar::tab {
                background-color: #3C3C3C;
                color: #CCCCCC;
                padding: 5px;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background-color: #505050;
                color: #FFFFFF;
            }
            QToolBar {
                background-color: #333333;
                padding: 5px;
            }
        """

        light_palette = """
            QMainWindow, QWidget {
                background-color: #FFFFFF;
                color: #000000;
                border: none;
            }
            QLineEdit, QPushButton {
                background-color: #F0F0F0;
                color: #000000;
                border: 1px solid #CCCCCC;
            }
            QLineEdit:focus, QPushButton:focus {
                border: 1px solid #AAAAAA;
            }
            QMenuBar, QMenu {
                background-color: #FFFFFF;
                color: #000000;
            }
            QMenu::item:selected {
                background-color: #DDDDDD;
            }
            QTabWidget::pane {
                border: 1px solid #CCCCCC;
                background-color: #F8F8F8;
            }
            QTabBar::tab {
                background-color: #E6E6E6;
                color: #333333;
                padding: 5px;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background-color: #CCCCCC;
                color: #000000;
            }
            QToolBar {
                background-color: #E0E0E0;
                padding: 5px;
            }
        """

        # Apply stylesheet based on mode
        if enabled:
            self.central_widget.setStyleSheet(dark_palette)
            self.title_bar.setStyleSheet("background-color: #444444;")
            self.title_label.setStyleSheet("color: white; font-size: 14px;")
            self.navigation_toolbar.setStyleSheet("background-color: #555555;")
        else:
            self.central_widget.setStyleSheet(light_palette)
            self.title_bar.setStyleSheet("background-color: #f0f0f0;")
            self.title_label.setStyleSheet("color: black; font-size: 14px;")
            self.navigation_toolbar.setStyleSheet("background-color: #E0E0E0;")

    def navigate_back(self):
        """Navigates back in the current tab."""
        current_widget = self.tab_widget.currentWidget()
        if isinstance(current_widget, QWebEngineView):
            current_widget.back()

    def navigate_forward(self):
        """Navigates forward in the current tab."""
        current_widget = self.tab_widget.currentWidget()
        if isinstance(current_widget, QWebEngineView):
            current_widget.forward()

    def reroll_page(self):
        """Regenerates the current website with a new idea."""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            return  

        current_title = self.tab_widget.tabText(current_index)
        if current_title.startswith("Building "):
            # Extract the original query
            query = current_title.replace("Building ", "")
            topic = query.replace(".gen", "").strip()
            if not topic:
                self.chat_display.append("Gen Browser: Invalid topic for reroll.")
                return
            # Create a new tab with loading screen
            self.create_new_tab(current_title, is_loading=True, base_topic=topic)
            self.generate_html_for_gen_site(topic, query, current_title)
        else:
            self.chat_display.append("Gen Browser: Current tab is not a generated website.")

    def navigate_home(self):
        """Navigates to the home page."""
        # Define a default home page or handle as needed
        home_html = """
        <html>
            <head>
                <title>Gen Browser Home</title>
                <style>
                    body {
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        font-family: Arial, sans-serif;
                        background-color: #f4f4f4;
                        color: #333;
                    }
                    h1 { color: #333; }
                    p { font-size: 1.2em; }
                </style>
            </head>
            <body>
                <h1>Welcome to Gen Browser!</h1>
                <p>Use the address bar above to generate dynamic websites on any topic by appending '.gen' to your query.</p>
            </body>
        </html>
        """
        # Create or navigate to a home tab
        for index in range(self.tab_widget.count()):
            if self.tab_widget.tabText(index) == "Home":
                self.tab_widget.setCurrentIndex(index)
                self.tab_widget.widget(index).setHtml(home_html)
                return
        # If Home tab doesn't exist, create it
        home_tab = QWebEngineView()
        home_tab.setHtml(home_html)
        self.tab_widget.addTab(home_tab, "Home")
        self.tab_widget.setCurrentWidget(home_tab)

    def toggle_fullscreen(self):
        """Toggles between fullscreen and maximized mode."""
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def generate_html_from_query(self, query):
        """Handles non-.gen queries (Placeholder)."""
        # Placeholder for handling non-.gen queries
        self.chat_display.append(f"Gen Browser: Handling non-.gen query '{query}' is not yet implemented.")

    def fetch_image(self, query):
        """Fetch a single image URL from Wikimedia Commons based on the query."""
        url = WIKIMEDIA_API_URL
        # First, search for images in the file namespace
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,  
            "srlimit": 20  
        }
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')
        try:
            response = requests.get(url, params=search_params)
            if response.status_code == 200:
                data = response.json()
                if "query" in data and "search" in data["query"]:
                    search_results = data["query"]["search"]
                    for result in search_results:
                        title = result['title']
                        # Now get imageinfo for this title
                        imageinfo_params = {
                            "action": "query",
                            "format": "json",
                            "titles": title,
                            "prop": "imageinfo",
                            "iiprop": "url|mime",
                            "iiurlwidth": 800,
                            "iiurlheight": 600
                        }
                        imageinfo_response = requests.get(url, params=imageinfo_params)
                        if imageinfo_response.status_code == 200:
                            imageinfo_data = imageinfo_response.json()
                            if "query" in imageinfo_data and "pages" in imageinfo_data["query"]:
                                page_data = next(iter(imageinfo_data["query"]["pages"].values()))
                                if "imageinfo" in page_data:
                                    imageinfo = page_data["imageinfo"][0]
                                    mime_type = imageinfo.get("mime", "")
                                    image_url = imageinfo.get("url", "")
                                    if mime_type.startswith("image/") and image_url.lower().endswith(valid_extensions):
                                        return image_url
                    # If no image found, use a default placeholder
                    print(f"No images found for query: {query}")
                    return "https://via.placeholder.com/300x200.png?text=No+Image"
                else:
                    print(f"No search results for query: {query}")
                    return "https://via.placeholder.com/300x200.png?text=No+Image"
            else:
                print(f"Failed to fetch image from Wikimedia Commons: {response.status_code}")
                return "https://via.placeholder.com/300x200.png?text=No+Image"
        except Exception as e:
            print(f"Exception while fetching image: {e}")
            return "https://via.placeholder.com/300x200.png?text=No+Image"

    def load_bookmarks(self):
        """Load bookmarks from a JSON file."""
        try:
            with open("bookmarks.json", "r") as file:
                self.bookmarks = json.load(file)
        except FileNotFoundError:
            self.bookmarks = {}
        except json.JSONDecodeError:
            self.bookmarks = {}

    def save_bookmarks(self):
        """Save bookmarks to a JSON file."""
        try:
            with open("bookmarks.json", "w") as file:
                json.dump(self.bookmarks, file, indent=4)
        except Exception as e:
            print(f"Failed to save bookmarks: {e}")

    def add_bookmark(self):
        """Add the current page to bookmarks."""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            QMessageBox.warning(self, "No Page", "There is no page to bookmark.")
            return
        current_title = self.tab_widget.tabText(current_index)
        current_tab = self.tab_widget.widget(current_index)
        if isinstance(current_tab, QWebEngineView):
            url = current_tab.url().toString()
        else:
            url = ""
        if not url:
            # For generated pages without a URL, we can use the title
            url = current_title

        # Use a dialog to get a name for the bookmark
        bookmark_name, ok = QInputDialog.getText(self, "Add Bookmark", "Bookmark Name:", QLineEdit.Normal, current_title)
        if ok and bookmark_name:
            self.bookmarks[bookmark_name] = url
            self.save_bookmarks()
            QMessageBox.information(self, "Bookmark Added", f"Bookmark '{bookmark_name}' added.")

    def generate_internal_page(self, base_topic, link_text, base_design):
        """Generates a page for an internal link."""
        page_type = link_text.strip('/')
        new_topic = f"{base_topic} - {page_type}"
        tab_title = f"Building {new_topic}.gen"
        self.create_new_tab(tab_title, is_loading=True, base_topic=base_topic, base_design=base_design)
        self.generate_html_for_gen_site(new_topic, f"{new_topic}.gen", tab_title, base_design)

    def generate_new_tab_from_link(self, link_text):
        """Generates a new tab for an external link."""
        new_topic = link_text.strip('/')
        tab_title = f"Building {new_topic}.gen"
        self.create_new_tab(tab_title, is_loading=True, base_topic=new_topic)
        self.generate_html_for_gen_site(new_topic, f"{new_topic}.gen", tab_title)

    def pull_model(self, model_name):
        """Pull the model if it's not available locally."""
        self.show_progress_dialog(f"Pulling model '{model_name}'...")
        try:
            for progress in ollama_client.pull(model_name):
                # Update progress bar
                self.update_progress_dialog(progress.get('progress', 0))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to pull model '{model_name}': {str(e)}")
            print(f"Failed to pull model '{model_name}': {e}")
        finally:
            self.hide_progress_dialog()

    def show_progress_dialog(self, message):
        """Display a progress dialog."""
        self.progress_dialog = QDialog(self)
        self.progress_dialog.setWindowTitle("Please Wait")
        self.progress_dialog.setFixedSize(300, 100)
        layout = QVBoxLayout()
        label = QLabel(message)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        layout.addWidget(label)
        layout.addWidget(self.progress_bar)
        self.progress_dialog.setLayout(layout)
        self.progress_dialog.show()

    def update_progress_dialog(self, progress):
        """Update the progress bar."""
        self.progress_bar.setValue(int(progress * 100))

    def hide_progress_dialog(self):
        """Hide the progress dialog."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None


class SignalCommunicator(QObject):
    """A helper class to define custom signals."""
    html_ready_signal = pyqtSignal(str, str)  


class ClosableTabBar(QTabBar):
    """Custom QTabBar that adds a close button to each tab."""
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        size.setWidth(size.width() + 25)  
        return size

    def paintEvent(self, event):
        """Custom paint event to draw close buttons."""
        painter = QStylePainter(self)
        option = QStyleOptionTab()

        for index in range(self.count()):
            self.initStyleOption(option, index)
            painter.drawControl(QStyle.CE_TabBarTab, option)

            # Draw the close button closer to the text
            rect = self.tabRect(index)
            icon = self.style().standardIcon(QStyle.SP_TitleBarCloseButton)
            # Adjust the close button position vertically centered
            close_rect = QRect(rect.right() - 20, rect.top() + (rect.height() - 16) // 2, 16, 16)
            icon.paint(painter, close_rect)

    def mousePressEvent(self, event):
        """Handles mouse press events to detect close button clicks."""
        # Check if the close button is clicked
        for index in range(self.count()):
            rect = self.tabRect(index)
            close_rect = QRect(rect.right() - 20, rect.top() + (rect.height() - 16) // 2, 16, 16)
            if close_rect.contains(event.pos()):
                self.parent().removeTab(index)  
                return
        super().mousePressEvent(event)


# Main application function
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gen Browser Prototype")
    browser = GenerativeBrowser()
    browser.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
