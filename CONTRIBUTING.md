# Contributing to Project Iceberg

Thanks for your interest in contributing! Project Iceberg is a local-first AI assistant, and we welcome contributions of all kinds.

## 🚀 Quick Start for Contributors

### Prerequisites
- Python 3.10+
- Node.js (for MCP servers)
- Git

### Setup

1. **Fork the repository** on GitHub

2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Project-Iceberg.git
   cd Project-Iceberg
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run Project Iceberg:**
   
   **Windows:**
   ```bash
   Launch.bat
   ```
   
   **Mac/Linux:**
   ```bash
   python server.py
   ```

5. **Open browser:** http://localhost:5000

## 🎯 What We Need Help With

### High Priority
- [ ] Additional MCP server integrations
- [ ] Mobile-responsive UI improvements
- [ ] Performance optimization for large tool sets
- [ ] Cross-platform testing (Mac/Linux)
- [ ] Documentation improvements

### Good First Issues
- [ ] Fix Windows path handling edge cases
- [ ] Add more LLM provider examples to README
- [ ] Improve Launch.bat error messages
- [ ] Add unit tests for tool registry
- [ ] Create example automation workflows

### Ideas Welcome
- Voice mode enhancements
- Custom theme support
- Plugin system for modules
- Integration with other local AI tools
- CLI improvements

## 📝 How to Submit Changes

### 1. Create a Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

**Branch naming:**
- `feature/` for new features
- `fix/` for bug fixes
- `docs/` for documentation
- `refactor/` for code improvements

### 2. Make Your Changes

**Code Style:**
- Follow PEP 8 for Python
- Use Black formatter: `black .`
- Use isort for imports: `isort .`
- Run linter: `ruff check .`

**Testing:**
- Add tests for new features in `tests/`
- Run existing tests: `pytest`
- Ensure tests pass before submitting

### 3. Commit Your Changes
```bash
git add .
git commit -m "Brief description of changes"
```

**Commit message format:**
- Start with a verb: "Add", "Fix", "Update", "Remove"
- Keep it under 72 characters
- Be descriptive but concise

**Examples:**
- ✅ "Add PostgreSQL MCP server to catalog"
- ✅ "Fix npx detection on Windows"
- ❌ "updates"
- ❌ "fixed stuff"

### 4. Push to Your Fork
```bash
git push origin feature/your-feature-name
```

### 5. Open a Pull Request

1. Go to the original Project-Iceberg repository
2. Click "New Pull Request"
3. Select your fork and branch
4. Fill out the PR template:
   - **What:** Brief description of changes
   - **Why:** Problem being solved or feature being added
   - **Testing:** How you tested the changes
   - **Screenshots:** If UI changes are involved

## 🐛 Reporting Bugs

**Before submitting:**
- Check if the issue already exists
- Try on the latest version
- Include reproduction steps

**Include in your bug report:**
- OS and version (Windows 11, macOS Sonoma, Ubuntu 22.04, etc.)
- Python version: `python --version`
- Node.js version: `node --version` (if MCP-related)
- LLM backend (Ollama, LM Studio, Anthropic)
- Error messages or logs
- Steps to reproduce

## 💡 Feature Requests

Open an issue with:
- **Problem:** What problem does this solve?
- **Solution:** Your proposed approach
- **Alternatives:** Other solutions you considered
- **Use Case:** Real-world scenario where this helps

## 🧪 Testing

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_core.py
```

### Run Tests with Coverage
```bash
pytest --cov=. --cov-report=html
```

## 📚 Documentation

Documentation improvements are always welcome!

**Where to contribute:**
- README.md - Getting started guide
- Code comments - Explain complex logic
- Docstrings - Function/class documentation
- Wiki - Tutorials and guides (coming soon)

## 🎨 UI/UX Contributions

The web UI lives in `ui/index.html`. It's a single-file design using:
- Vanilla JavaScript (no framework)
- CSS custom properties for theming
- Flask backend API

**Before making major UI changes:**
1. Open an issue to discuss
2. Share mockups or sketches
3. Consider mobile responsiveness

## 🔧 Development Tips

### Project Structure
```
Project-Iceberg/
├── agent_core/       # Core agent logic
├── agents/           # Orchestrator agent
├── executor/         # Tool execution engine
├── modules/          # Personality modules
├── planner/          # LLM planning logic
├── tools/            # Built-in tools & MCP loader
├── ui/               # Web interface
├── server.py         # Flask web server
├── main.py           # CLI entry point
└── tests/            # Test suite
```

### Useful Commands
```bash
# Format code
black . && isort .

# Check for issues
ruff check .

# Start with debug mode
python server.py --debug

# Clear memory/logs for clean testing
rm memory_store.json logs/*.log
```

### Adding a New MCP Server to Catalog

Edit `tools/mcp_catalog.py`:
```python
{
    "name": "your-server",
    "display_name": "🔧 Your Server",
    "description": "What it does",
    "command": "npx",
    "args": ["-y", "@scope/server-name"],
    "env": {},
    "requires_api_key": False,
}
```

## ❓ Questions?

- **GitHub Issues:** For bugs and feature requests
- **Discussions:** For questions and ideas (coming soon)
- **Pull Requests:** For code review and feedback

## 📜 Code of Conduct

Be respectful and constructive. We're all here to build something cool together.

**Expected behavior:**
- Be welcoming to newcomers
- Respect different viewpoints
- Accept constructive criticism gracefully
- Focus on what's best for the project

**Unacceptable behavior:**
- Harassment or discriminatory language
- Personal attacks
- Spam or off-topic content
- Publishing others' private information

## 🎉 Recognition

Contributors will be:
- Listed in release notes
- Credited in README (coming soon)
- Thanked publicly for significant contributions

Thank you for contributing to Project Iceberg! 🧊
