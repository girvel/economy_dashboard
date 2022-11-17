import os
from datetime import date, timedelta
from pathlib import Path

import dash_bootstrap_components as dbc
import dash_bootstrap_templates as dbt
import yaml
from dash import Dash, html, dcc, Output, Input, State
import pandas
import plotly.express as px


categories = {
    "tran": "Transportation",
    "groc": "Groceries",
    "cafe": "Cafe",
    "meds": "Health",
    "clothes": "Clothes",
    "util": "Rent",
    "rent": "Rent",
    "cup": "Home",
    "tech": "Home",
    "pty": "Caprice",
    "game": "Caprice",
    "save": "Savings",
    "lost": "Unaccounted",
    "lenses": "Health",
    "docs": "Taxes, documents & other",
}

uncontrolled_categories = {
    'Clothes', 'Health', 'Transportation', 'Rent', 'Savings',
    "Taxes, documents & other"
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
        df = df.reindex(
            pandas.date_range(min(df.index), max(df.index)),
            fill_value=0
        )

        return df.reset_index(names=["date"])

def polish(df):
    df = df.copy()

    df["date"] = df["date"].dt.strftime("%Y.%m.%d %H:%M")
    del df["comment"]
    df = df[["date", "amount", "category"]]

    return df

dbt.load_figure_template("LUX")
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
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

    balance = sum(df["amount"])

    start_date = pandas.Timestamp(start_date)
    end_date = pandas.Timestamp(end_date) + timedelta(days=1)

    df = df[(start_date <= df["date"]) & (df["date"] <= end_date)]

    if len(df) == 0:
        return "No transactions"

    df["category"] = df["comment"].map(lambda c: categories.get(c, c))
    dt = end_date - start_date

    spent = Spendings(df)
    all_categories = sorted(set(spent.df['category']))
    controlled_categories = sorted(
        set(all_categories) - uncontrolled_categories
    )

    udf = spent.df.copy()
    udf = udf[udf["category"].isin(uncontrolled_categories)]
    uncontrolled_spent = sum(udf["amount"])

    sdf = spent.df.copy()
    sdf = sdf[sdf["category"].isin(controlled_categories)]
    controlled_spent = sum(sdf['amount'])

    idf = df.copy()
    idf = df[df["amount"] > 0]
    controlled_income = sum(idf["amount"]) - uncontrolled_spent

    return [
        dcc.Store(id='limited_df', data=df.to_json(orient="records")),
        html.H3("Transactions"),
        html.P(f"Balance is {balance:,} AMD"),
        html.P(f"{dt.days} days, {controlled_spent:,} AMD, {controlled_spent / dt.days:,.0f} AMD/day"),
        html.P(f"Expected {controlled_income / 30.5 * dt.days:,.0f} AMD, {controlled_income / 30.5:,.0f} AMD/day"),
        html.P(f"Uncontrollable spendings: {uncontrolled_spent:,} AMD"),
        dbc.Row([
            dbc.Col([
                dbc.Table.from_dataframe(polish(df)),
            ]),
            dbc.Col([
                html.Div([
                    dbc.Checklist(
                        options=[
                            {"label": "Include uncontrolled",
                             "value": "uncontrolled"},
                        ],
                        value=[],
                        inline=True,
                        id='categories_pie_flags'
                    ),
                    dcc.Graph(
                        id='categories_pie'
                    ),
                ]),

                html.Div([
                    dbc.Checklist(
                        options=[{"label": c, "value": c} for c in all_categories],
                        value=controlled_categories,
                        inline=True,
                        id='categories_checklist'
                    ),
                    dcc.Graph(
                        id='spent_by_day',
                    ),
                ]),
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


@app.callback(
    Output('categories_pie', 'figure'),
    [Input('categories_pie_flags', 'value'),
     State('limited_df', 'data')]
)
def render_categories_pie(flags, df):
    df = pandas.read_json(df)

    if "uncontrolled" not in flags:
        df = df[~df["category"].isin(uncontrolled_categories)]

    spent = Spendings(df)

    return px.pie(
        spent.by_category(),
        values="amount",
        names="category",
        title="Categories",
    )


if __name__ == "__main__":
    app.run(debug=True)
