output "alb_dns_name" {
  description = "Open this in a browser to reach SafeClick through the load balancer."
  value       = "http://${aws_lb.web.dns_name}"
}

output "asg_name" {
  description = "Auto Scaling group name."
  value       = aws_autoscaling_group.web.name
}

output "target_group_arn" {
  description = "Target group ARN."
  value       = aws_lb_target_group.web.arn
}

output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}
