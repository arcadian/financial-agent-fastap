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
  - `"decrease banking by 10% in P1"`

### 3. Advanced Portfolio Adjustments

- **Shift Weight Between Sectors:** (Moves weight from one sector to others, leaving the rest of the portfolio untouched)
  - `"shift 5% from financials and give it to energy in P1"`
- **Batch Adjust Multiple Sectors:** (Adjusts multiple sectors at once against the remainder of the portfolio)
  - `"in P1, increase energy by 4% and decrease textiles by 1%"`

### 4. Portfolio State Management

- **Reset Portfolio:**
  - `"reset P1"`
  - `"revert portfolio P1 to its initial state"`

---

## Advanced Execution Patterns

This agent is capable of understanding and executing complex queries by breaking them down into a staged plan, running independent tasks in parallel, and managing dependencies between tasks.

### 1. Example: Parallel Execution (Independent Tasks)

This showcases tasks that can run concurrently because they don't depend on each other's results or on a preceding state-changing operation.

- **Command:** `"what are the sectors for BBID1 and BBID3 and what are the top 3 energy names for P1?"`

- **How it works:**
    - **Planner's Output:** The LLM planner will generate a plan with a single stage containing two independent tool calls:
      ```json
      {
        "plan": [
          [
            { "tool_name": "lookup_sectors", "parameters": { "asset_ids": ["BBID1", "BBID3"] } },
            { "tool_name": "show_top_constituents", "parameters": { "portfolio_id": "P1", "n": 3, "sector": "Energy" } }
          ]
        ]
      }
      ```
    - **Orchestrator's Action:** The orchestrator sees these two tasks in the same stage. Since both are "read" operations and don't depend on each other, it executes them **in parallel** using `asyncio.gather()`. Both results will be returned once they are complete.

### 2. Example: Sequential Execution (State Dependency)

This demonstrates how the agent respects implicit dependencies where a "write" operation must occur after a "read" operation to ensure data consistency.

- **Command:** `"set energy to 15% in P1 and then show me the top 6 names in that sector"`

- **How it works:**
    - **Planner's Output:** The LLM planner generates a plan with two sequential stages:
      ```json
      {
        "plan": [
          [ { "tool_name": "adjust_sector_exposure", "parameters": { "portfolio_id": "P1", "sector": "Energy", "set_weight": 0.15 } } ],
          [ { "tool_name": "show_top_constituents", "parameters": { "portfolio_id": "P1", "n": 6, "sector": "Energy" } } ]
        ]
      }
      ```
    - **Orchestrator's Action:** The orchestrator executes Stage 1 first. It waits for the `adjust_sector_exposure` tool (a "write" operation) to complete, which modifies the portfolio's state. Only after this is done will it proceed to execute Stage 2, ensuring that the `show_top_constituents` command operates on the newly adjusted portfolio.

### 3. Example: Chained Dependency (Output as Input)

This is a direct data dependency, where the output of one tool is explicitly used as the input for the next.

- **Command:** `"show me the sectors for the top 5 assets in P100"`

- **How it works:**
    - **Planner's Output:** The LLM planner generates a plan with two sequential stages:
      ```json
      {
        "plan": [
          [ { "tool_name": "show_top_constituents", "parameters": { "portfolio_id": "P100", "n": 5 } } ],
          [ { "tool_name": "lookup_sectors", "parameters": { "asset_ids": "$PREVIOUS_STAGE_OUTPUT" } } ]
        ]
      }
      ```
    - **Orchestrator's Action:** The orchestrator executes Stage 1. It then captures the list of asset IDs from Stage 1's result and injects them as the `asset_ids` parameter for the `lookup_sectors` tool in Stage 2. This ensures the `lookup_sectors` tool operates on the exact assets identified in the previous step.

---

## API Endpoints

The backend service exposes the following endpoints:

#### `GET /`
- **Description:** Serves the main HTML web page with the chat interface.
- **Response:** The `index.html` file.

#### `POST /portfolio/adjust-from-text`
- **Description:** The primary "agent" endpoint. It processes a natural language query, determines intent, executes tools, and returns the result(s).
- **Request Body:** `{"query": "your query here"}`
- **Response:** A JSON object containing a list of `results` from the one or more commands that were executed.

#### `POST /assets/lookup-sectors`
- **Description:** Performs a fast, bulk lookup to find the sector for each asset ID in a given list.
- **Request Body:** `{"asset_ids": ["BBID1", "BBID4001"]}`
- **Response:** A JSON dictionary mapping each asset ID to its sector name.

#### `POST /assets/lookup-prices`
- **Description:** Performs a fast, bulk lookup to find the price for a given list of asset IDs.
- **Request Body:** `{"asset_ids": ["BBID1", "BBID4001"]}`
- **Response:** A JSON dictionary mapping each asset ID to its price.

#### `GET /docs`
- **Description:** Provides a rich, interactive API documentation page using the Swagger UI. You can view all available endpoints, see their required parameters, and even test them live by sending requests directly from the browser page.

#### `GET /redoc`
- **Description:** Provides alternative, more formal API documentation (ReDoc).

#### `GET /static/{file_path}`
- **Description:** This endpoint is automatically created by the line `app.mount("/static", ...)` and is responsible for serving any static files (like CSS, JavaScript, or images) that are placed in the `static` directory.

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