# Screenshot checklist

Save screenshots in `docs/screenshots/` using these names so the README links work.

## Setup
- [x] `01-vpc-subnets.png`: VPC with both public subnets and the route table
- [x] `02-security-groups.png`: ALB and web security group rules
- [x] `03-launch-template.png`: launch template summary (t2.micro, security group, LabInstanceProfile, user data)
- [x] `04-alb-active.png`: load balancer with DNS name and Active status
- [x] `05-asg-details.png`: Auto Scaling group details (min 1, desired 1, max 2)
- [x] `06-running-instance.png`: one running instance
- [x] `07-safeclick-browser.png`: SafeClick in the browser through the ALB DNS name, with a scan result

## Scaling
- [x] `08-cloudwatch-cpu.png`: CloudWatch CPU climbing above 40%
- [x] `09-asg-scale-out.png`: Activity tab showing the new instance launch
- [x] `10-two-instances.png`: EC2 showing two running instances
- [x] `11-two-instance-ids.png`: browser or curl loop showing both instance IDs
- [x] `11b-safeclick-second-az.png`: SafeClick page served from the second Availability Zone
- [x] `12-health-check-settings.png`: target group health check settings (path, interval, thresholds)

## Failure recovery
- [x] `13-availability-loop.png`: terminal loop showing Status: 200 during the failure
- [x] `14-asg-replacement.png`: Activity tab showing the replacement launch

## Documentation
- [x] `architecture.png`: exported architecture diagram (saved in `docs/`, not `docs/screenshots/`)
