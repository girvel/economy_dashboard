import os
from datetime import date, timedelta
from pathlib import Path

import dash_bootstrap_components as dbc
import dash_bootstrap_templates as dbt
import yaml
from dash import Dash, html, dcc, Output, Input, State
import pandas
from tiny_storage import Unit
import plotly.express as px


def generate_table(dataframe):
    return html.Table([
        html.Thead(
            html.Tr([html.Th(col) for col in dataframe.columns])
        ),
        html.Tbody([
            html.Tr([
                html.Td(dataframe.iloc[i][col]) for col in dataframe.columns
            ]) for i in range(len(dataframe))
        ])
    ])

categories = {
    "tran": "Transportation",
    "groc": "Groceries & etc",
    "cafe": "Cafe",
    "meds": "Drugs",
    "clothes": "Clothes",
}

class Spendings:
    def __init__(self, df):
        df = df.copy()
        df = df[df["amount"] < 0]
        df["amount"] *= -1
        self.df = df

    def by_category(self):
        df = self.df.copy()

        df = df.groupby(["category"]).sum()
        return df.reset_index(level=0)

    def by_day(self):
        df = self.df.copy()

        df["date"] = df["date"].dt.date
        df = df.groupby(["date"]).sum(numeric_only=True)
        return df.reset_index(level=0)

def polish(df):
    df = df.copy()
    df["date"] = df["date"].dt.strftime("%Y.%m.%d %H:%M")
    return df

transactions_config = Unit("todoist_transactions")

dbt.load_figure_template("LUX")
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.LUX],
    suppress_callback_exceptions=True
)

app.layout = html.Div([
    dcc.Location(id='url', refresh=True),
    dcc.Store(id='df'),
    dcc.DatePickerRange(
        id='date_range',
        initial_visible_month=date.today(),
    ),
    html.Div(id="main"),
])


@app.callback(
    Output('df', 'data'),
    [Input('url', 'pathname')]
)
def query_and_save_df(pathname):
    os.system(
        "wsl -e scp -i /mnt/d/Downloads/Main.pem "
        "ubuntu@aws.girvel.xyz:/mine/data/transactions.yaml "
        "transactions.yaml"
    )

    df = pandas.json_normalize(yaml.safe_load(
        Path("transactions.yaml").read_text()
    ))

    df = df[["date", "comment", "amount"]]
    df = df.sort_values(["date"], ascending=False)

    return df.to_json(orient="records")


@app.callback(
    [Output('date_range', 'min_date_allowed'),
     Output('date_range', 'max_date_allowed'),
     Output('date_range', 'start_date'),
     Output('date_range', 'end_date')],
    [Input('df', 'data')]
)
def determine_date_limits(df):
    df = pandas.read_json(df)

    return [
        min(df["date"]),
        max(df["date"]),
        df[df["comment"] == "salary"]["date"].iloc[0],
        max(df["date"]),
    ]


@app.callback(
    Output('main', 'children'),
    [Input('date_range', 'start_date'),
     Input('date_range', 'end_date'),
     State('df', 'data'),],
)
def display_page(start_date, end_date, df):
    df = pandas.read_json(df)

    start_date = pandas.Timestamp(start_date)
    end_date = pandas.Timestamp(end_date) + timedelta(days=1)

    df = df[(start_date <= df["date"]) & (df["date"] <= end_date)]

    if len(df) == 0:
        return "No transactions"

    df["category"] = df["comment"].map(lambda c: categories.get(c, c))
    dt = end_date - start_date

    spent = Spendings(df)
    total_spent = sum(spent.df['amount'])
    balance = sum(df["amount"])
    income = 801_970 - 332_000
    all_categories = sorted(set(spent.df['category']))
    uncontrolled_categories = {'Clothes', 'Drugs', 'Transportation'}
    controlled_categories = sorted(
        set(all_categories) - uncontrolled_categories
    )

    return [
        dcc.Store(id='limited_df', data=df.to_json(orient="records")),
        html.H3("Transactions"),
        html.P(f"Balance is {balance:,} AMD"),
        html.P(f"{dt.days} days, {total_spent:,} AMD, {total_spent / dt.days:,.0f} AMD/day"),
        html.P(f"Expected {income / 30.5 * dt.days:,.0f} AMD, {income / 30.5:,.0f} AMD/day"),
        dbc.Row([
            dbc.Col([
                generate_table(polish(df)),
            ]),
            dbc.Col([
                dcc.Graph(
                    figure=px.pie(
                        spent.by_category(),
                        values="amount",
                        names="category",
                        title="Categories",
                    )
                ),
                dcc.Checklist(
                    options=all_categories,
                    value=controlled_categories,
                    labelStyle={
                        'margin-right': '10px',
                    },
                    id='categories_checklist'
                ),
                dcc.Graph(
                    id='spent_by_day',
                ),
            ]),
        ]),
    ]


@app.callback(
    Output('spent_by_day', 'figure'),
    [Input('categories_checklist', 'value'),
     State('limited_df', 'data')]
)
def render_line_graph(categories, df):
    df = pandas.read_json(df)
    df = df[df["category"].isin(categories)]
    spent = Spendings(df)

    return px.line(
        spent.by_day(),
        x="date",
        y="amount",
        line_shape="spline",
        title="By day",
    )


if __name__ == "__main__":
    app.run(debug=True)
