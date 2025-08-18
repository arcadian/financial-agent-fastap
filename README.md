# Financial Portfolio Agent

This project is a sophisticated financial agent powered by a FastAPI backend and a Large Language Model (LLM). It provides a natural language chat interface to manage and query a simulated financial portfolio, supporting a wide range of commands from simple lookups to complex, multi-step transactions.

## Key Features

- **Natural Language Interface:** Interact with the portfolio using plain English commands.
- **Multi-Command Execution:** The agent can parse and execute multiple commands from a single query.
- **Chain of Thought Reasoning:** For complex queries, the agent can perform a sequence of actions, using the output of one step as the input for the next.
- **State Management:** The agent maintains the state of the portfolio throughout a session and supports resetting to its initial state.
- **Confidence-Based Actions:** The agent evaluates its confidence in understanding a query and will reject commands it's not sure about to prevent errors.
- **Auto-Generated API Docs:** Leverages FastAPI to provide interactive API documentation.

---

## Supported Commands

The agent understands a wide variety of commands, which can be combined in a single query.

### 1. Basic Lookups & Queries

- **Show Top Constituents (Entire Portfolio):**
  - `"show top 10 constituents in P1"`
- **Show Top Constituents (Filtered by Sector):**
  - `"show top 5 names in banking for P1"`
- **Show Constituents with Sector Info:**
  - `"show the top 10 constituents in P1 with their sectors"`
- **Look Up Arbitrary Assets:**
  - `"what is the sector for BBID999"`

### 2. Simple Portfolio Adjustments

- **Set an Absolute Target Weight:**
  - `"set textiles to 25% in P1"`
- **Increase by a Relative Amount:**
  - `"increase energy by 3.5% in P1"`
- **Decrease by a Relative Amount:**
  - `"decrease industrials by 10% in P1"`

### 3. Advanced Portfolio Adjustments

- **Shift Weight Between Sectors:** (Moves weight from one sector to others, leaving the rest of the portfolio untouched)
  - `"shift 5% from financials and give it to energy in P1"`
- **Batch Adjust Multiple Sectors:** (Adjusts multiple sectors at once against the remainder of the portfolio)
  - `"in P1, increase energy by 4% and decrease textiles by 1%"`

### 4. Portfolio State Management

- **Reset Portfolio:**
  - `"reset P1"`
  - `"revert portfolio P1 to its initial state"`

### 5. Chained Commands (Chain of Thought)

- **Action then Verification:**
  - `"increase energy in P1 by 5% and then show me the top 5 constituents in that sector"`
- **Complex Sequences:**
  - `"reset P1, set banking to 20%, and finally show the top 10 names in the banking sector"`

---

## API Endpoints

The backend service exposes the following endpoints:

#### `GET /`
- **Description:** Serves the main HTML web page with the chat interface.
- **Response:** The `index.html` file.

#### `POST /portfolio/adjust-from-text`
- **Description:** The primary "agent" endpoint. It processes a natural language query, determines intent, executes tools, and returns the result(s).
- **Request Body:** `{"query": "your query here"}`
- **Response:** A JSON object containing a list of `results` from the executed commands.

#### `POST /assets/lookup-sectors`
- **Description:** Performs a fast, bulk lookup to find the sector for each asset ID in a given list.
- **Request Body:** `{"asset_ids": ["BBID1", "BBID4001"]}`
- **Response:** A JSON dictionary mapping each asset ID to its sector name.

#### `GET /docs`
- **Description:** Provides interactive API documentation (Swagger UI) where you can view and test all endpoints directly from your browser.

#### `GET /redoc`
- **Description:** Provides alternative, formal API documentation (ReDoc).

---

## Getting Started

### Prerequisites

- Python 3.8+
- An active OpenAI API key.

### Installation and Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your API Key:**
    - Rename the `.env.example` file to `.env`.
    - Open the `.env` file and replace the placeholder with your actual OpenAI API key:
      ```
      OPENAI_API_KEY="your_openai_api_key_here"
      ```

### Running the Application

1.  **Start the server:**
    ```bash
    uvicorn main:app --reload
    ```

2.  **Access the application:**
    - **Web Interface:** Open your browser and go to `http://127.0.0.1:8000/`
    - **API Docs:** To test the API directly, go to `http://127.0.0.1:8000/docs`
