import argparse
import subprocess


def run(*args):
    subprocess.run(['gcloud', *args], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default='europe-west1')
    parser.add_argument('--schedule-uri', required=True)
    parser.add_argument('--apply', action='store_true')
    options = parser.parse_args()
    if not options.apply:
        parser.error('Deployment creates billable GCP resources. Review README and pass --apply.')
    project, region = options.project, options.region
    if not options.schedule_uri.startswith('gs://') or ',' in options.schedule_uri:
        parser.error('--schedule-uri must be a gs://bucket/file.ics URI without commas')
    common = ['--project', project, '--quiet']
    job = 'liza-homework'
    worker = f'{job}@{project}.iam.gserviceaccount.com'
    scheduler = f'{job}-cron@{project}.iam.gserviceaccount.com'
    run('services', 'enable', 'run.googleapis.com', 'cloudscheduler.googleapis.com',
        'cloudbuild.googleapis.com', 'artifactregistry.googleapis.com', 'secretmanager.googleapis.com', *common)
    for account in [job, job + '-cron']:
        exists = subprocess.run(['gcloud', 'iam', 'service-accounts', 'describe',
                                 f'{account}@{project}.iam.gserviceaccount.com', *common], capture_output=True)
        if exists.returncode:
            run('iam', 'service-accounts', 'create', account, *common)
    secrets = ['WEBTOP_WEB_TOKEN', 'WEBTOP_STUDENT',
               'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
    for secret in secrets:
        run('secrets', 'describe', secret, *common)
        run('secrets', 'add-iam-policy-binding', secret, '--member', 'serviceAccount:' + worker,
            '--role', 'roles/secretmanager.secretAccessor', *common)
    image = f'{region}-docker.pkg.dev/{project}/{job}/bot:latest'
    exists = subprocess.run(['gcloud', 'artifacts', 'repositories', 'describe', job,
                             '--location', region, *common], capture_output=True)
    if exists.returncode:
        run('artifacts', 'repositories', 'create', job, '--repository-format=docker', '--location', region, *common)
    run('builds', 'submit', '.', '--tag', image, *common)
    bucket = options.schedule_uri[5:].split('/', 1)[0]
    run('storage', 'buckets', 'add-iam-policy-binding', 'gs://' + bucket,
        '--member', 'serviceAccount:' + worker, '--role', 'roles/storage.objectViewer', *common)
    run('run', 'jobs', 'deploy', job, '--image', image, '--region', region, '--service-account', worker,
        '--memory', '2Gi', '--cpu', '1', '--task-timeout', '900s', '--max-retries', '0', '--tasks', '1',
        '--set-secrets', ','.join(f'{secret}={secret}:latest' for secret in secrets),
        '--set-env-vars', 'LOOKBACK_WEEKS=4,SCHEDULE_URI=' + options.schedule_uri, *common)
    run('run', 'jobs', 'add-iam-policy-binding', job, '--region', region,
        '--member', 'serviceAccount:' + scheduler, '--role', 'roles/run.invoker', *common)
    exists = subprocess.run(['gcloud', 'scheduler', 'jobs', 'describe', job, '--location', region, *common], capture_output=True)
    action = 'update' if exists.returncode == 0 else 'create'
    run('scheduler', 'jobs', action, 'http', job, '--location', region, '--schedule', '0 16 * * *',
        '--time-zone', 'Asia/Jerusalem', '--uri', f'https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run',
        '--http-method', 'POST', '--oauth-service-account-email', scheduler, '--message-body', '{}',
        '--max-retry-attempts', '0', *common)


if __name__ == '__main__':
    main()
