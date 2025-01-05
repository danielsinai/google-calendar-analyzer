import os
import datetime
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_calendar_service():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)

def get_events(service, time_window_start, time_window_end):
    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_window_start.isoformat() + 'Z',
        timeMax=time_window_end.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])

def is_working_hours(event_start):
    """Check if event is during working hours (9 AM - 6 PM)"""
    hour = event_start.hour
    return 9 <= hour < 18

def is_working_day(event_date):
    """Check if event is on a working day (Sunday-Thursday)"""
    return event_date.weekday() < 5

def analyze_calendar_data(events):
    event_data = []
    
    for event in events:
        start = event['start'].get('dateTime')
        if not start:  # Skip all-day events
            continue
            
        start_time = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
        duration = (datetime.datetime.fromisoformat(event['end'].get('dateTime').replace('Z', '+00:00')) - 
                   start_time).total_seconds() / 3600  # Convert to hours
        
        response_status = 'Not Responded'
        for attendee in event.get('attendees', []):
            if attendee.get('self', False):
                response_status = attendee.get('responseStatus', 'Not Responded')
                break
        
        event_data.append({
            'date': start_time.date(),
            'start_time': start_time,
            'duration': duration,
            'response_status': response_status,
            'during_working_hours': is_working_hours(start_time),
            'during_working_days': is_working_day(start_time)
        })
    
    return pd.DataFrame(event_data)

def calculate_meeting_metrics(df, start_date, end_date):
    # Calculate working days in the period
    total_working_days = sum(1 for date in pd.date_range(start_date, end_date) 
                            if date.weekday() < 5)
    working_hours_per_day = 8  # 9 AM - 5 PM
    total_working_hours = total_working_days * working_hours_per_day
    
    metrics = {}
    for status in ['accepted', 'declined', 'needsAction', 'tentative']:
        status_df = df[df['response_status'] == status]
        
        # Total hours in meetings
        metrics[f'{status}_total_hours'] = status_df['duration'].sum()
        
        # Percentage of working hours
        metrics[f'{status}_percentage'] = (metrics[f'{status}_total_hours'] / total_working_hours) * 100
        
        # Working hours vs non-working hours
        working_hours = status_df[status_df['during_working_hours']]['duration'].sum()
        non_working_hours = status_df[~status_df['during_working_hours']]['duration'].sum()
        metrics[f'{status}_working_hours'] = working_hours
        metrics[f'{status}_non_working_hours'] = non_working_hours
    
    return metrics

def create_visualization(metrics):
    # Modern color scheme
    colors = {
        'accepted': '#00B894',    # Fresh mint green
        'declined': '#FF7675',    # Soft red
        'needsAction': '#74B9FF', # Soft blue
        'tentative': '#FDCB6E'    # Warm yellow
    }
    
    # Create figure with secondary y-axis
    fig = make_subplots(
        rows=1, cols=1,
        specs=[[{"secondary_y": True}]],
        subplot_titles=["Meeting Time Analysis"]
    )
    
    statuses = ['accepted', 'declined', 'needsAction', 'tentative']
    status_names = {
        'accepted': 'Accepted',
        'declined': 'Declined',
        'needsAction': 'Pending',
        'tentative': 'Tentative'
    }
    
    # Add traces for each status
    for status in statuses:
        # Add bars for total hours
        fig.add_trace(
            go.Bar(
                name=f"{status_names[status]} Meetings",
                x=[status_names[status]],
                y=[metrics[f'{status}_total_hours']],
                marker_color=colors[status],
                hovertemplate="<b>%{x}</b><br>" +
                             "Total Hours: %{y:.1f}<br>" +
                             f"Working Hours: {metrics[f'{status}_working_hours']:.1f}<br>" +
                             f"Non-Working Hours: {metrics[f'{status}_non_working_hours']:.1f}<extra></extra>"
            ),
            secondary_y=False
        )
        
        # Add markers for percentage
        fig.add_trace(
            go.Scatter(
                name=f"{status_names[status]} (%)",
                x=[status_names[status]],
                y=[metrics[f'{status}_percentage']],
                mode='markers',
                marker=dict(
                    size=20,
                    symbol='diamond',
                    color=colors[status],
                    line=dict(color='white', width=2)
                ),
                hovertemplate="<b>%{x}</b><br>" +
                             "Percentage of Working Hours: %{y:.1f}%<extra></extra>"
            ),
            secondary_y=True
        )
    
    # Update layout with modern styling
    fig.update_layout(
        title=dict(
            text='Meeting Time Analysis',
            font=dict(size=24, color='#2D3436'),
            x=0.5,
            y=0.95
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        barmode='group',
        bargap=0.15,
        bargroupgap=0.1,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5
        ),
        margin=dict(t=100, l=70, r=70, b=100),
        font=dict(family="Arial, sans-serif", size=12, color='#2D3436')
    )
    
    # Update axes
    fig.update_xaxes(
        showgrid=False,
        showline=True,
        linecolor='#DFE6E9',
        tickfont=dict(size=12)
    )
    
    fig.update_yaxes(
        title_text="Total Hours",
        showgrid=True,
        gridcolor='#DFE6E9',
        showline=True,
        linecolor='#DFE6E9',
        tickformat='.1f',
        secondary_y=False,
        tickfont=dict(size=12),
        title_font=dict(size=14)
    )
    
    fig.update_yaxes(
        title_text="Percentage of Working Hours",
        showgrid=False,
        showline=True,
        linecolor='#DFE6E9',
        tickformat='.1f',
        ticksuffix='%',
        secondary_y=True,
        tickfont=dict(size=12),
        title_font=dict(size=14)
    )
    
    # Show the plot
    fig.show()

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Analyze Google Calendar meetings within a time window')
    parser.add_argument('--start', '-s', type=str, required=True,
                      help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end', '-e', type=str, required=True,
                      help='End date in YYYY-MM-DD format')
    
    args = parser.parse_args()
    
    try:
        start_date = datetime.datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(args.end, '%Y-%m-%d')
    except ValueError as e:
        print("Error: Dates must be in YYYY-MM-DD format")
        return
    
    if end_date < start_date:
        print("Error: End date must be after start date")
        return
    
    # Get Google Calendar service
    service = get_calendar_service()
    
    # Get events
    events = get_events(service, start_date, end_date)
    
    # Analyze data
    df = analyze_calendar_data(events)
    
    # Calculate metrics
    metrics = calculate_meeting_metrics(df, start_date, end_date)
    
    # Create and show visualization
    create_visualization(metrics)

if __name__ == '__main__':
    main() 