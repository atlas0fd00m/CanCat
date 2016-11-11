#include <stdint.h>

#ifndef __QUEUE_H__
#define __QUEUE_H__

template <class T>
class Queue { 
   private: 
      T* items;
      volatile uint32_t head;
      volatile uint32_t tail;
      uint32_t num_items; 

   public:
      ~Queue() { delete items; }
      bool isEmpty() { return head == tail; }

      Queue(uint32_t num);
      bool enqueue(T const*);
      T dequeue();
}; 

/* Constructor. Allocate buffer */
template <class T>
Queue<T>::Queue(uint32_t num)
{
    head = 0;
    tail = 0;
    num_items = num;
    items = new T[num];
}
 
template <class T>
bool Queue<T>::enqueue (T const* item) {
    if((tail + 1) % num_items == head) // Buffer is full
        return false;
    items[tail] = *item;
    tail++;

    if(tail >= num_items)
    {
        tail = 0;
    }
    return true;
} 

template <class T>
T Queue<T>::dequeue () {
    T item;
    #warning "Need to do error checking here too"
    if(isEmpty())
    {
        return item;
    }

    item = items[head];
    head++;

    if(head >= num_items)
    {
        head = 0;
    }
    return item;
} 

#endif
