import os
from datetime import date
from pathlib import Path

import dash_bootstrap_components as dbc
import dash_bootstrap_templates as dbt
import yaml
from dash import Dash, html, dcc, Output, Input
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

def total_spendings(df):
    df = df.copy()

    df = df[df["amount"] < 0]
    df["amount"] *= -1
    df = df.groupby(["category"]).sum()
    return df.reset_index(level=0)

def polish(df):
    df = df.copy()
    df["date"] = df["date"].dt.strftime("%Y.%m.%d %H:%M")
    return df

transactions_config = Unit("todoist_transactions")

dbt.load_figure_template("LUX")
app = Dash(__name__, external_stylesheets=[dbc.themes.LUX])
app.layout = html.Div([
    dcc.Location(id='url', refresh=True),
    dcc.DatePickerRange(
        id='date_range',
        initial_visible_month=date.today(),
    ),
    html.Div(id="main"),
])


@app.callback(
    Output('main', 'children'),
    [Input('url', 'pathname'),
     Input('date_range', 'start_date'),
     Input('date_range', 'end_date')],
)
def display_page(pathname, start_date, end_date):
    start_date = start_date \
        and pandas.Timestamp(start_date) \
        or pandas.Timestamp.min
    end_date = end_date \
        and pandas.Timestamp(end_date) \
        or pandas.Timestamp.max

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
    df = df[(start_date <= df["date"]) & (df["date"] <= end_date)]

    if len(df) == 0:
        return "No transactions"

    df["category"] = df["comment"].map(lambda c: categories.get(c, c))
    dt = max(df['date']) - min(df['date'])

    spendings = total_spendings(df)
    total_spent = sum(spendings['amount'])
    balance = sum(df["amount"])
    income = 651_970 - 332_000

    return [
        html.H3("Transactions"),
        html.P(f"Balance is {balance:,} AMD"),
        html.P(f"{dt.days} days, {total_spent:,} AMD, {total_spent / dt.days:,.0f} AMD/day"),
        html.P(f"Expected {income / 30.5 * dt.days:,.0f} AMD, {income / 30.5:,.0f} AMD/day"),
        dcc.Graph(
            figure=px.pie(
                spendings,
                values="amount",
                names="category",
                title="Spendings",
            )
        ),
        generate_table(polish(df)),
    ]


if __name__ == "__main__":
    app.run(debug=True)
