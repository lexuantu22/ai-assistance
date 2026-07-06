# Use Nginx directly
FROM nginx:alpine

# Copy built assets from local build (via GH actions)
COPY dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
